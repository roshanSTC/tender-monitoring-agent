import sqlite3
import json
from typing import List, Optional, Dict, Any
from config.settings import DB_PATH
from core.models import TenderRecord, BidDecisionStatus, TenderAnalysisReport
from core.logger import get_agent_logger

logger = get_agent_logger("Database")

class TenderDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                organization TEXT NOT NULL,
                portal TEXT NOT NULL,
                published_date TEXT,
                due_date TEXT NOT NULL,
                estimated_value_inr REAL,
                emd_amount_inr REAL,
                category TEXT,
                location TEXT,
                doc_path TEXT,
                doc_url TEXT,
                match_score INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                analysis_report_json TEXT,
                corrigendums_json TEXT,
                created_at TEXT NOT NULL
            )
            ''')
            conn.commit()

    def save_tender(self, tender: TenderRecord) -> None:
        report_json = tender.analysis_report.model_dump_json() if tender.analysis_report else None
        corrigendums_json = json.dumps([c.model_dump() if hasattr(c, 'model_dump') else c for c in tender.corrigendums])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO tenders (
                id, title, organization, portal, published_date, due_date,
                estimated_value_inr, emd_amount_inr, category, location,
                doc_path, doc_url, match_score, status, analysis_report_json,
                corrigendums_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                organization=excluded.organization,
                due_date=excluded.due_date,
                estimated_value_inr=excluded.estimated_value_inr,
                emd_amount_inr=excluded.emd_amount_inr,
                match_score=excluded.match_score,
                status=excluded.status,
                analysis_report_json=excluded.analysis_report_json,
                corrigendums_json=excluded.corrigendums_json
            ''', (
                tender.id, tender.title, tender.organization, tender.portal.value if hasattr(tender.portal, 'value') else tender.portal,
                tender.published_date, tender.due_date, tender.estimated_value_inr,
                tender.emd_amount_inr, tender.category, tender.location,
                tender.doc_path, tender.doc_url, tender.match_score,
                tender.status.value if hasattr(tender.status, 'value') else tender.status,
                report_json, corrigendums_json, tender.created_at
            ))
            conn.commit()
            logger.info(f"Tender record persisted: [{tender.id}] - Score: {tender.match_score}%, Status: {tender.status.value if hasattr(tender.status, 'value') else tender.status}")

    def get_all_tenders(self) -> List[TenderRecord]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenders ORDER BY due_date ASC")
            rows = cursor.fetchall()
            
            tenders = []
            for row in rows:
                row_dict = dict(row)
                report_json = row_dict.get("analysis_report_json")
                if report_json:
                    row_dict["analysis_report"] = TenderAnalysisReport.model_validate_json(report_json)
                corrigendums_json = row_dict.get("corrigendums_json")
                if corrigendums_json:
                    row_dict["corrigendums"] = json.loads(corrigendums_json)
                tenders.append(TenderRecord(**row_dict))
            return tenders

    def get_tender_by_id(self, tender_id: str) -> Optional[TenderRecord]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tenders WHERE id = ?", (tender_id,))
            row = cursor.fetchone()
            if not row:
                return None
            row_dict = dict(row)
            if row_dict.get("analysis_report_json"):
                row_dict["analysis_report"] = TenderAnalysisReport.model_validate_json(row_dict["analysis_report_json"])
            if row_dict.get("corrigendums_json"):
                row_dict["corrigendums"] = json.loads(row_dict["corrigendums_json"])
            return TenderRecord(**row_dict)

    def update_status(self, tender_id: str, new_status: BidDecisionStatus) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tenders SET status = ? WHERE id = ?", (new_status.value, tender_id))
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Updated status for Tender [{tender_id}] -> {new_status.value}")
            return success

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tenders")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tenders WHERE match_score >= 70")
            high_match = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tenders WHERE status = ?", (BidDecisionStatus.PURSUING.value,))
            pursuing = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(estimated_value_inr) FROM tenders WHERE status = ?", (BidDecisionStatus.PURSUING.value,))
            pursuing_value = cursor.fetchone()[0] or 0.0
            return {
                "total_tenders": total,
                "high_match_count": high_match,
                "pursuing_count": pursuing,
                "pursuing_value_inr": pursuing_value
            }
