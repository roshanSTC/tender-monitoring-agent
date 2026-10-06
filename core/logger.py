import os
import sys
import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List
from config.settings import LOGS_DIR, LOG_FILE_PATH, AUDIT_LOG_PATH

# Ensure logs directory exists
LOGS_DIR.mkdir(parents=True, exist_ok=True)

class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured text with standardized timestamps and context."""
    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", "GLOBAL")
        component = getattr(record, "component", record.name)
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{timestamp}] [{record.levelname:7s}] [{component}] [Trace:{trace_id}] {record.getMessage()}"

def get_agent_logger(name: str = "TenderAgent", level: int = logging.INFO) -> logging.Logger:
    """Returns a production-configured logger with rotation and console output."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    # 1. Rotating File Handler (10MB max, up to 5 rolling backups)
    file_handler = RotatingFileHandler(
        filename=str(LOG_FILE_PATH),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(file_handler)

    # 2. Console Stream Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

class ScrapingAuditLogger:
    """
    Dedicated audit logger for tracking every web scraping request,
    target portal URL, HTTP status code, latency, and extraction stats in JSONL.
    """
    @staticmethod
    def record_event(
        action: str,
        target_portal: str,
        target_url: str,
        http_status: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        payload_bytes: Optional[int] = None,
        tenders_discovered: int = 0,
        details: Optional[str] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        event = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "target_portal": target_portal,
            "target_url": target_url,
            "http_status": http_status,
            "response_time_ms": round(response_time_ms, 2) if response_time_ms is not None else None,
            "payload_bytes": payload_bytes,
            "tenders_discovered": tenders_discovered,
            "details": details or "",
            "error": error or None
        }

        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            get_agent_logger("AuditLogger").error(f"Failed to write audit event: {e}")

        return event

    @staticmethod
    def get_recent_audit_events(limit: int = 50) -> List[Dict[str, Any]]:
        """Reads the most recent audit entries from JSONL."""
        if not AUDIT_LOG_PATH.exists():
            return []
        events = []
        try:
            with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            continue
        except Exception:
            return []
        return events[-limit:][::-1]  # Return newest first

    @staticmethod
    def get_recent_raw_logs(limit_lines: int = 200) -> List[str]:
        """Reads the latest lines from the main rotating log file."""
        if not LOG_FILE_PATH.exists():
            return []
        try:
            with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return [line.strip() for line in lines[-limit_lines:][::-1]]
        except Exception:
            return []
