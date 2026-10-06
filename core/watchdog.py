import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from core.scraper import IndianTenderScraper
from core.database import TenderDatabase
from core.notifier import EmailNotifier
from core.logger import get_agent_logger, ScrapingAuditLogger

logger = get_agent_logger("Watchdog")

class AutonomousWatchdogService:
    """
    Autonomous background worker that polls registered procurement portals,
    detects new bids and amendments, evaluates compliance, and sends email alerts.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AutonomousWatchdogService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.is_running = False
        self.stop_requested = False
        self.thread: Optional[threading.Thread] = None
        self.last_run_time: Optional[datetime] = None
        self.next_run_time: Optional[datetime] = None
        self.total_cycles = 0
        self.new_tenders_found = 0
        self.alerts_dispatched = 0
        self.last_status_message = "Watchdog initialized (Idle)"

    @classmethod
    def get_instance(cls) -> "AutonomousWatchdogService":
        return cls()

    def start(self) -> bool:
        """Starts the autonomous watchdog background daemon thread."""
        with self._lock:
            if self.is_running:
                logger.warning("Watchdog service is already active.")
                return False

            self.is_running = True
            self.stop_requested = False
            self.thread = threading.Thread(target=self._run_loop, name="TenderWatchdogThread", daemon=True)
            self.thread.start()
            self.last_status_message = "Autonomous Watchdog daemon running in background"
            logger.info("Autonomous Watchdog Service started successfully.")
            return True

    def stop(self) -> bool:
        """Stops the autonomous background worker."""
        with self._lock:
            if not self.is_running:
                return False
            self.stop_requested = True
            self.is_running = False
            self.last_status_message = "Watchdog service stopped by user"
            logger.info("Autonomous Watchdog Service stopped.")
            return True

    def run_cycle_now(self) -> Dict[str, Any]:
        """Executes an immediate manual probe cycle synchronously."""
        logger.info("Manual watchdog probe cycle triggered.")
        return self._execute_cycle()

    def _run_loop(self):
        logger.info("Watchdog background thread loop started.")
        while not self.stop_requested:
            cfg = EmailNotifier.load_config()
            interval_min = int(cfg.get("watchdog_interval_minutes", 180))

            self._execute_cycle()

            self.next_run_time = datetime.now() + timedelta(minutes=interval_min)
            sleep_seconds = interval_min * 60

            # Sleep in small slices to respond promptly to stop_requested
            for _ in range(sleep_seconds // 2):
                if self.stop_requested:
                    break
                time.sleep(2)

        self.is_running = False
        logger.info("Watchdog background loop terminated.")

    def _execute_cycle(self) -> Dict[str, Any]:
        cycle_start = datetime.now()
        self.last_run_time = cycle_start
        self.total_cycles += 1
        
        logger.info(f"--- Starting Autonomous Watchdog Cycle #{self.total_cycles} ---")
        
        db = TenderDatabase()
        scraper = IndianTenderScraper()
        email_cfg = EmailNotifier.load_config()

        email_enabled = email_cfg.get("enabled", False)
        min_score = int(email_cfg.get("min_alert_score", 75))
        notify_corrigendum = email_cfg.get("notify_on_corrigendum", True)

        discovered_this_cycle = 0
        alerts_this_cycle = 0
        new_records = []

        try:
            # 1. Fetch live tenders from registered portals
            scraped_tenders = scraper.fetch_curated_indian_tenders()
            existing_tenders = {t.id: t for t in db.get_all_tenders()}

            for t in scraped_tenders:
                if t.id not in existing_tenders:
                    # New tender discovered!
                    discovered_this_cycle += 1
                    self.new_tenders_found += 1
                    db.save_tender(t)
                    new_records.append(t)

                    # Check if qualified for instant email alert
                    if email_enabled and t.match_score >= min_score:
                        logger.info(f"Dispatching instant email alert for high-match tender [{t.id}] ({t.match_score}%)...")
                        success, status_msg = EmailNotifier.send_tender_alert(t)
                        if success:
                            alerts_this_cycle += 1
                            self.alerts_dispatched += 1
                else:
                    # Check for new corrigendums on existing tenders
                    existing = existing_tenders[t.id]
                    if len(t.corrigendums) > len(existing.corrigendums):
                        new_corrigendums = t.corrigendums[len(existing.corrigendums):]
                        existing.corrigendums = t.corrigendums
                        db.save_tender(existing)

                        if email_enabled and notify_corrigendum:
                            for c in new_corrigendums:
                                EmailNotifier.send_corrigendum_alert(existing, c)
                                alerts_this_cycle += 1
                                self.alerts_dispatched += 1

            self.last_status_message = f"Cycle #{self.total_cycles} complete at {datetime.now().strftime('%H:%M:%S')} (New Bids: {discovered_this_cycle}, Alerts: {alerts_this_cycle})"
            logger.info(self.last_status_message)

            ScrapingAuditLogger.record_event(
                action="WATCHDOG_CYCLE_COMPLETED",
                target_portal="ALL_REGISTERED",
                target_url="AUTO_BACKGROUND",
                http_status=200,
                response_time_ms=(datetime.now() - cycle_start).total_seconds() * 1000,
                tenders_discovered=discovered_this_cycle,
                details=f"Watchdog Cycle #{self.total_cycles}: Discovered {discovered_this_cycle} new tenders, Dispatched {alerts_this_cycle} email alerts."
            )

            return {
                "success": True,
                "cycle": self.total_cycles,
                "new_tenders": discovered_this_cycle,
                "alerts_sent": alerts_this_cycle,
                "timestamp": self.last_run_time.strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            err_msg = f"Watchdog Cycle #{self.total_cycles} encountered error: {str(e)}"
            logger.error(err_msg)
            self.last_status_message = err_msg
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def get_status(self) -> Dict[str, Any]:
        cfg = EmailNotifier.load_config()
        interval_min = int(cfg.get("watchdog_interval_minutes", 180))

        return {
            "is_running": self.is_running,
            "total_cycles": self.total_cycles,
            "new_tenders_found": self.new_tenders_found,
            "alerts_dispatched": self.alerts_dispatched,
            "last_run_time": self.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_run_time else "Never",
            "next_run_time": self.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if self.next_run_time else "Scheduled after start",
            "status_message": self.last_status_message,
            "interval_minutes": interval_min,
            "email_enabled": cfg.get("enabled", False)
        }
