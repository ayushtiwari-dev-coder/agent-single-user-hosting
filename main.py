# main.py
import sys
import argparse

# Enforce UTF-8 safely to avoid local system terminal encoding crashes
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Initialize paths and load environment variables
from utils.path_helper import load_env_file

load_env_file()

from database.table_generator import create_tables
from cli.menu_flows import run_main_app_loop


def start_cli():
    """Boots the standard Terminal CLI interface."""
    run_main_app_loop()


def start_telegram():
    """Boots the Telegram Long-Polling Bot."""
    try:
        from interfaces.telegram_bot import run_telegram_bot

        run_telegram_bot()
    except ImportError as e:
        print(
            f"\n[Error] Failed to load Telegram bot. Did you install pyTelegramBotAPI?"
        )
        print(f"Details: {e}")
        sys.exit(1)


def start_web():
    """Boots the FastAPI backend for the React UI."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from interfaces.websocket import router as websocket_router

    print("\n[Notice] Starting FastAPI Web Server on ws://localhost:8000...")
    
    app = FastAPI(title="Local Agent API")
    
    # Add CORS middleware so React (port 5173) can talk to FastAPI (port 8000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Safe for local development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Plug in the WebSocket router you already built
    app.include_router(websocket_router)
    
    # Start the server
    uvicorn.run(app, host="127.0.0.1", port=8000)


def main():
    """Main Entrypoint Router for the Local Workflow Agent."""
    print("Initializing local assistant database...")
    try:
        create_tables()
    except Exception as e:
        print(f"Fatal: Database setup failed: {e}")
        sys.exit(1)

    # 1. Parse Command Line Arguments (For automated background running)
    parser = argparse.ArgumentParser(description="Launch the Local AI Agent")
    parser.add_argument(
        "--mode",
        choices=["cli", "telegram", "web"],
        help="Bypass the menu and directly launch a specific interface.",
    )
    args = parser.parse_args()

    # If an argument was passed, route directly to it
    if args.mode == "cli":
        start_cli()
        return
    elif args.mode == "telegram":
        start_telegram()
        return
    elif args.mode == "web":
        start_web()
        return

    # 2. Interactive Startup Menu (If no arguments were passed)
    while True:
        print("\n" + "=" * 60)
        print("🤖 LOCAL WORKFLOW AGENT - STARTUP MENU")
        print("=" * 60)
        print(" [1] Standard CLI (Terminal)")
        print(" [2] Telegram Bot (Remote Access)")
        print(" [3] Web UI (React - Coming Soon)")
        print(" [4] Exit")
        print("=" * 60)

        choice = input(" Select interface (1-4): ").strip()

        if choice == "1":
            start_cli()
            break
        elif choice == "2":
            start_telegram()
            break
        elif choice == "3":
            start_web()
            break
        elif choice == "4" or choice.lower() in ["exit", "quit"]:
            print("Exiting...")
            sys.exit(0)
        else:
            print(" Invalid selection. Please choose 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()
