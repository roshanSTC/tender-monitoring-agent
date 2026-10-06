import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
TENDERS_DIR = DATA_DIR / "tenders"
DB_PATH = DATA_DIR / "tenders.db"

DATA_DIR.mkdir(exist_ok=True)
TENDERS_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

GEM_PORTAL_URL = "https://gem.gov.in"
CPPP_PORTAL_URL = "https://eprocure.gov.in/eprocure/app"

POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))
COMPANY_PROFILE_PATH = CONFIG_DIR / "company_profile.json"

# Production Logging Configuration
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE_PATH = LOGS_DIR / "tender_agent.log"
AUDIT_LOG_PATH = LOGS_DIR / "scraping_audit.jsonl"

