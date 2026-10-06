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
PORTALS_CONFIG_PATH = CONFIG_DIR / "monitored_portals.json"
EMAIL_CONFIG_PATH = CONFIG_DIR / "email_config.json"

# Static SMTP Sender Gateway Configuration (Handled in code / .env, hidden from UI)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_SENDER_NAME = os.getenv("SMTP_SENDER_NAME", "TenderPulse Procurement Intelligence")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "True").lower() in ("true", "1", "yes")

