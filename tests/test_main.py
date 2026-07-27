# tests/test_main.py
import pytest
from unittest.mock import patch, MagicMock
import main

def test_health_check():
    """Ensures the FastAPI health endpoint returns the correct status."""
    response = main.health_check()
    assert response == {"status": "ok", "agent": "running"}

@patch("main.REPO_ID", "mock_repo_id")
@patch("main.api")
@patch("main.os.makedirs")
def test_restore_db_on_boot_success(mock_makedirs, mock_api):
    """Ensures DB is downloaded from Hugging Face if configured."""
    main.restore_db_on_boot()
    mock_makedirs.assert_called_once()
    mock_api.hf_hub_download.assert_called_once_with(
        repo_id="mock_repo_id", 
        repo_type="dataset", 
        filename="assistant.db",
        local_dir=main.APP_DIR
    )

@patch("main.REPO_ID", None)
@patch("main.api")
def test_restore_db_on_boot_missing_config(mock_api):
    """Ensures restore aborts safely if Hugging Face is not configured."""
    main.restore_db_on_boot()
    mock_api.hf_hub_download.assert_not_called()

@patch("main.REPO_ID", "mock_repo_id")
@patch("main.api")
@patch("main.os.path.exists", return_value=True)
@patch("main.time.sleep", side_effect=[None, InterruptedError("Break Loop")]) # <--- FIXED HERE
def test_backup_db_loop(mock_sleep, mock_exists, mock_api):
    """Ensures the backup loop uploads the DB to Hugging Face."""
    with pytest.raises(InterruptedError):
        main.backup_db_loop()
    
    mock_api.upload_file.assert_called_once()

def test_restore_db_on_boot_hf_exception():
    """Edge Case: If Hugging Face Hub is down during boot, the app must not crash."""
    with patch("main.REPO_ID", "mock_repo_id"), \
         patch("main.api") as mock_api:
        
        # Simulate a network crash during download
        mock_api.hf_hub_download.side_effect = Exception("HF Hub 503 Service Unavailable")
        
        # This should catch the exception internally and print a notice, NOT raise it
        main.restore_db_on_boot()

def test_backup_db_loop_upload_exception():
    """Edge Case: If the backup loop fails to upload, it must not kill the background thread."""
    with patch("main.REPO_ID", "mock_repo_id"), \
         patch("main.api") as mock_api, \
         patch("main.os.path.exists", return_value=True), \
         patch("main.time.sleep", side_effect=[None, InterruptedError("Break Loop")]):
        
        # Simulate a network crash during upload
        mock_api.upload_file.side_effect = Exception("Connection Reset by Peer")
        
        with pytest.raises(InterruptedError):
            main.backup_db_loop()
        
        # Ensure it attempted the upload and caught the error safely
        mock_api.upload_file.assert_called_once()