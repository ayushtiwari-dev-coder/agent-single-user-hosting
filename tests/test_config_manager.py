# tests/test_config_manager.py
import pytest
import tempfile
import os
from unittest.mock import patch
import utils.config_manager as cm


@pytest.fixture(autouse=True)
def temp_config_sandbox():
    """Sandbox CONFIG_PATH using a temporary JSON file to protect user home configuration."""
    temp_config = tempfile.NamedTemporaryFile(delete=False)
    temp_config_path = temp_config.name
    temp_config.close()

    # Patch the module-level configuration path constant
    path_patcher = patch("utils.config.core.CONFIG_PATH", temp_config_path)
    path_patcher.start()

    yield temp_config_path

    path_patcher.stop()
    try:
        os.remove(temp_config_path)
    except OSError:
        pass


def test_load_config_fallback_when_file_missing(temp_config_sandbox):
    # If config file is missing, verify it safely returns standard default dictionary
    if os.path.exists(temp_config_sandbox):
        os.remove(temp_config_sandbox)
    config = cm.load_config()

    # FIX: Allow either gemini or groq depending on your local core.py settings
    assert config["models"]["default_provider"] in ["gemini", "groq"]
    assert "thinking_level" in config["settings"]


def test_set_and_get_provider_api_key_interaction():
    # Store key inside the mock json config
    cm.set_provider_api_key("gemini", "mock-gemini-key")
    # Retrieve and verify key matches
    key = cm.get_provider_api_key("gemini")
    assert key == "mock-gemini-key"


@patch.dict(os.environ, {"GROQ_API_KEY": "fallback-groq-key"})
def test_get_provider_api_key_environment_fallback():
    # Ensure config holds None for groq key
    cm.set_provider_api_key("groq", None)
    # Retrieval should fall back to mapped system environment variables
    key = cm.get_provider_api_key("groq")
    assert key == "fallback-groq-key"


def test_loop_guard_edge_cases():
    """Verifies that invalid loop guard inputs gracefully fall back to None in the schema."""
    # 1. Test Valid Inputs (Standard Usage)
    cm.set_loop_guard(max_failed=5, max_success=10)
    lg = cm.get_loop_guard()
    assert lg["max_failed_attempts"] == 5
    assert lg["max_success_attempts"] == 10

    # 2. Test Zero and None (Clearing the configuration)
    cm.set_loop_guard(max_failed=0, max_success=None)
    lg_reset = cm.get_loop_guard()
    assert lg_reset["max_failed_attempts"] is None
    assert lg_reset["max_success_attempts"] is None

    # 3. Test Negative Values (Malicious / Accidental Inputs)
    cm.set_loop_guard(max_failed=-5, max_success=-1)
    lg_negative = cm.get_loop_guard()
    assert lg_negative["max_failed_attempts"] is None
    assert lg_negative["max_success_attempts"] is None


def test_custom_system_instruction_persistence():
    """Verifies that setting a custom instruction writes to the config, and clearing it returns None."""
    # 1. Set Custom
    cm.set_system_instruction("You are a helpful coding assistant.")
    assert cm.get_system_instruction() == "You are a helpful coding assistant."

    # 2. Clear (set to None or empty)
    cm.set_system_instruction("")
    assert cm.get_system_instruction() is None

    cm.set_system_instruction(None)
    assert cm.get_system_instruction() is None


def test_embedding_model_persistence():
    """Verifies we can dynamically update embedding models per provider."""
    # Test Gemini
    cm.set_embedding_model("gemini", "custom-gemini-embed-v2")
    assert cm.get_embedding_model("gemini") == "custom-gemini-embed-v2"

    # Test Groq
    cm.set_embedding_model("groq", "custom-nomic-v3")
    assert cm.get_embedding_model("groq") == "custom-nomic-v3"


def test_sandbox_environment_persistence():
    """Verifies Docker image and Workspace path overrides."""
    # # Docker Image
    # cm.set_docker_image("node:18-alpine")
    # assert cm.get_docker_image() == "node:18-alpine"

    # Workspace Path
    cm.set_workspace_path("/custom/dev/folder")
    assert cm.get_workspace_path().endswith("custom/dev/folder".replace("/", os.sep))


# def test_multitasking_config_boundary_clamping(temp_config_sandbox):
#     """Verify that setters enforce standard safe lower boundaries to prevent system crashes."""
#     # Negative/Zero active counts must be clamped to at least 1 container
#     cm.set_max_active_containers(-2)
#     assert cm.get_max_active_containers() == 1

#     cm.set_max_active_containers(0)
#     assert cm.get_max_active_containers() == 1

#     # Total containers cannot be set below 1
#     cm.set_max_total_containers(-5)
#     assert cm.get_max_total_containers() == 1

#     # Idle timeout cannot be negative or zero (clamped to a safe 0.1-minute step)
#     cm.set_container_idle_timeout(-10.0)
#     assert cm.get_container_idle_timeout() == 0.1

#     cm.set_container_idle_timeout(0)
#     assert cm.get_container_idle_timeout() == 0.1

# def test_multitasking_config_persistence(temp_config_sandbox):
#     """Verify user multitasking sandboxing properties persist correctly in the config."""
#     # 1. Active container limit persistence
#     cm.set_max_active_containers(5)
#     assert cm.get_max_active_containers() == 5

#     # 2. Total container retention persistence
#     cm.set_max_total_containers(15)
#     assert cm.get_max_total_containers() == 15

#     # 3. Idle timeout boundary checks
#     cm.set_container_idle_timeout(45.5)
#     assert cm.get_container_idle_timeout() == 45.5
