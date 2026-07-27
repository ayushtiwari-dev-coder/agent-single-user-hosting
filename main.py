# main.py
import os
import time
import threading
import uvicorn
from fastapi import FastAPI
from huggingface_hub import HfApi

from database.connection import DATABASE_PATH, APP_DIR
from database.table_generator import create_tables
from interfaces.telegram_bot import run_telegram_bot
from queries.scheduler_queries import reset_orphaned_tasks


app = FastAPI(title="Hosted Agent Web Server")

# -------------------------------------------------------------------
# HUGGING FACE DATASET PERSISTENCE
# -------------------------------------------------------------------
REPO_ID = os.environ.get("HF_DATASET_ID")
HF_TOKEN = os.environ.get("HF_TOKEN")

api = HfApi(token=HF_TOKEN) if HF_TOKEN else None

def restore_db_on_boot():
    if not REPO_ID or not api:
        print("[Notice] HF_DATASET_ID or HF_TOKEN missing. Running in ephemeral storage mode.")
        return
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        api.hf_hub_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            filename="assistant.db",
            local_dir=APP_DIR
        )
        print("[Success] Restored assistant.db from Hugging Face Dataset!")
    except Exception as e:
        print(f"[Notice] No existing DB found in dataset (first boot): {e}")

def backup_db_loop():
    if not REPO_ID or not api:
        return
    while True:
        time.sleep(300) # Sync every 5 minutes
        if os.path.exists(DATABASE_PATH):
            try:
                api.upload_file(
                    path_or_fileobj=DATABASE_PATH,
                    path_in_repo="assistant.db",
                    repo_id=REPO_ID,
                    repo_type="dataset",
                    commit_message="Automated SQLite backup"
                )
            except Exception as e:
                print(f"[Backup Error] Failed to sync database: {e}")

# -------------------------------------------------------------------
# FASTAPI HEALTH ENDPOINT (For Keep-Alive Pings)
# -------------------------------------------------------------------
@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "ok", "agent": "running"}

if __name__ == "__main__":
    print("Booting Hosted Agent System...")
    
    restore_db_on_boot()
    create_tables()
    reset_orphaned_tasks()
    
    from interfaces.telegram_bot import run_telegram_bot, start_scheduler_loop
    
    threading.Thread(target=backup_db_loop, daemon=True).start()
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    
    # Start the Scheduler Loop!
    threading.Thread(target=start_scheduler_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting Keep-Alive HTTP Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)