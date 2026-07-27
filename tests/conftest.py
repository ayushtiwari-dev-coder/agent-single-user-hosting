# tests/conftest.py
import os

# Inject fake environment variables globally BEFORE any test or module is imported.
# This prevents top-level module code (like telegram_bot.py or main.py) from 
# crashing with exit(1) or missing key errors during the test suite run.

os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:fake_telegram_token_for_testing"
os.environ["GEMINI_API_KEY"] = "fake_gemini_key"
os.environ["GROQ_API_KEY"] = "fake_groq_key"
os.environ["HF_TOKEN"] = "fake_hf_token"
os.environ["HF_DATASET_ID"] = "fake_repo_id"
os.environ["JINA_API_KEY"] = "fake_jina_key"
os.environ["TELEGRAM_ALLOWED_USERS"] = "12345,67890"

print("\n[pytest] Injected fake environment variables via conftest.py\n")