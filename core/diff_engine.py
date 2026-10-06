import re
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from core.models import TenderRecord, Corrigendum, DiffItem
from core.analyzer import TenderAnalyzer
from core.logger import get_agent_logger

logger = get_agent_logger("DiffEngine")

class CorrigendumDiffEngine:
    """
    Procurement-aware Differential Analysis Engine.
    Detects date extensions, financial relaxations, technical amendments,
    and calculates impact on company eligibility.
    """

    def __init__(self, analyzer: Optional[TenderAnalyzer] = None):
        self.analyzer = analyzer or TenderAnalyzer()

    def compare(
        self,
        tender: TenderRecord,
        corrigendum_text: str,
        corrigendum_id: str = "CORR-01",
        published_date: Optional[str] = None,
        doc_url: Optional[str] = None
    ) -> Corrigendum:
        """
        Compares corrigendum text against an existing TenderRecord.
        Produces structured DiffItems and computes qualification impact.
        """
        logger.info(f"Running Corrigendum Auto-Diff for Tender [{tender.id}] against {corrigendum_id}")
        diff_items: List[DiffItem] = []
        amended_fields: List[str] = []
        text_lower = corrigendum_text.lower()
        now_str = published_date or datetime.now().strftime("%Y-%m-%d")

        # 1. Submission Deadline / Due Date Diff
        date_diff = self._detect_date_extension(tender.due_date, corrigendum_text)
        if date_diff:
            diff_items.append(date_diff)
            amended_fields.append("Submission Deadline")

        # 2. Turnover Requirement Diff
        turnover_diff = self._detect_turnover_change(tender, corrigendum_text)
        if turnover_diff:
            diff_items.append(turnover_diff)
            amended_fields.append("Annual Turnover Criteria")

        # 3. EMD & Fee Exemption Diff
        emd_diff = self._detect_emd_change(tender, corrigendum_text)
        if emd_diff:
            diff_items.append(emd_diff)
            amended_fields.append("Earnest Money Deposit (EMD)")

        # 4. Performance Security / PBG Diff
        pbg_diff = self._detect_pbg_change(corrigendum_text)
        if pbg_diff:
            diff_items.append(pbg_diff)
            amended_fields.append("Performance Bank Guarantee (PBG)")

        # 5. Delivery Period Diff
        delivery_diff = self._detect_delivery_change(corrigendum_text)
        if delivery_diff:
            diff_items.append(delivery_diff)
            amended_fields.append("Delivery & Execution Timeline")

        # 6. Clause Substitutions ("Read XYZ instead of ABC")
        clause_diffs = self._detect_clause_substitutions(corrigendum_text)
        for cd in clause_diffs:
            diff_items.append(cd)
            if "Technical Specification" not in amended_fields:
                amended_fields.append("Technical Specification")

        # If no specific patterns detected, generate a generic informational item
        if not diff_items:
            summary_snippet = corrigendum_text[:120].strip().replace("\n", " ") + "..."
            diff_items.append(DiffItem(
                parameter="General Terms & Addendum Notice",
                original_value="Original Tender Schedule Terms",
                amended_value=summary_snippet,
                delta_summary="General Text Amendment",
                severity="Informational",
                action_required="Review published addendum notice text"
            ))
            amended_fields.append("General Terms")

        # Re-score evaluation with amended terms
        old_score = tender.match_score
        new_due_date = next((di.amended_value for di in diff_items if di.parameter == "Submission Due Date"), tender.due_date)
        
        simulated_metadata = {
            "organization": tender.organization,
            "due_date": new_due_date,
            "estimated_value_inr": tender.estimated_value_inr,
            "emd_amount_inr": tender.emd_amount_inr
        }

        re_eval_report = self.analyzer.analyze_tender(
            tender_title=tender.title,
            tender_text=f"{tender.title}. {corrigendum_text}",
            metadata=simulated_metadata
        )
        new_score = re_eval_report.overall_match_score

        if new_score > old_score:
            impact_msg = f"Score increased from {old_score}% to {new_score}% (Criteria relaxed)"
        elif new_score < old_score:
            impact_msg = f"Score adjusted from {old_score}% to {new_score}% (Conditions updated)"
        else:
            impact_msg = f"Maintains {old_score}% ({re_eval_report.qualification_status}) qualification status"

        description_summary = "; ".join([f"{d.parameter}: {d.delta_summary}" for d in diff_items])

        return Corrigendum(
            corrigendum_id=corrigendum_id,
            tender_id=tender.id,
            published_date=now_str,
            description=description_summary,
            amended_fields=amended_fields,
            document_url=doc_url,
            diff_items=diff_items,
            qualification_impact=impact_msg,
            old_score=old_score,
            new_score=new_score
        )

    def _detect_date_extension(self, original_due_str: str, text: str) -> Optional[DiffItem]:
        # Date regex for formats: DD.MM.YYYY, DD-MM-YYYY, YYYY-MM-DD
        date_pattern = r"\b(\d{2}[-/\.]\d{2}[-/\.]\d{4}|\d{4}[-/\.]\d{2}[-/\.]\d{2})\b"
        
        # Look for explicit read/instead of for dates
        m_read = re.search(r"(?:read|extended to|revised to|closing date[:\s\-]*|submission date[:\s\-]*)\s*" + date_pattern, text, re.IGNORECASE)
        if m_read:
            raw_new = m_read.group(1).replace("/", "-").replace(".", "-")
            clean_new = self._normalize_date(raw_new)
            clean_orig = self._normalize_date(original_due_str)

            if clean_new and clean_orig and clean_new != clean_orig:
                delta_days = (clean_new - clean_orig).days
                delta_str = f"+{delta_days} Days Extension" if delta_days > 0 else f"{delta_days} Days"
                return DiffItem(
                    parameter="Submission Due Date",
                    original_value=clean_orig.strftime("%Y-%m-%d"),
                    amended_value=clean_new.strftime("%Y-%m-%d"),
                    delta_summary=delta_str,
                    severity="Critical",
                    action_required="Reschedule bid submission & extend Bank Guarantee validity"
                )

        # Look for keywords like "extended by X days"
        m_by_days = re.search(r"extended\s+by\s+(\d+)\s+days?", text, re.IGNORECASE)
        if m_by_days:
            days = int(m_by_days.group(1))
            clean_orig = self._normalize_date(original_due_str)
            if clean_orig:
                from datetime import timedelta
                new_date = clean_orig + timedelta(days=days)
                return DiffItem(
                    parameter="Submission Due Date",
                    original_value=clean_orig.strftime("%Y-%m-%d"),
                    amended_value=new_date.strftime("%Y-%m-%d"),
                    delta_summary=f"+{days} Days Extension",
                    severity="Critical",
                    action_required="Update bid schedule and ensure DSC validity"
                )
        return None

    def _detect_turnover_change(self, tender: TenderRecord, text: str) -> Optional[DiffItem]:
        m = re.search(r"turnover.*?(?:read|revised|amended|reduced|relaxed)\s*(?:to)?[:\s\-₹rs\.]*(\d+(?:\.\d+)?)\s*(cr|crore|lakh)", text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            val_cr = val if "cr" in unit or "crore" in unit else val / 100.0
            orig_val_cr = (tender.estimated_value_inr * 0.4 / 10000000.0) if tender.estimated_value_inr else 15.0

            return DiffItem(
                parameter="Annual Turnover Criteria",
                original_value=f"₹{orig_val_cr:.2f} Cr (Original 40% Benchmark)",
                amended_value=f"₹{val_cr:.2f} Cr",
                delta_summary=f"Turnover threshold relaxed to ₹{val_cr:.2f} Cr",
                severity="Critical",
                action_required="Verify against CA-audited balance sheet credentials"
            )
        return None

    def _detect_emd_change(self, tender: TenderRecord, text: str) -> Optional[DiffItem]:
        if "msme" in text.lower() and ("exempt" in text.lower() or "waiver" in text.lower()):
            orig_emd = f"₹{tender.emd_amount_inr/100000:.2f} Lakhs" if tender.emd_amount_inr else "Specified in NIT"
            return DiffItem(
                parameter="Earnest Money Deposit (EMD)",
                original_value=orig_emd,
                amended_value="Exempted for MSME / Udyam / Startups",
                delta_summary="Full EMD Fee Waiver for MSME bidders",
                severity="Critical",
                action_required="Attach valid Udyam Registration Certificate in Packet-A"
            )
        return None

    def _detect_pbg_change(self, text: str) -> Optional[DiffItem]:
        m = re.search(r"(?:pbg|performance security|performance bank guarantee).*?(?:reduced|revised|read)\s*(?:to)?[:\s\-]*(\d+)%", text, re.IGNORECASE)
        if m:
            new_pbg = m.group(1)
            return DiffItem(
                parameter="Performance Bank Guarantee (PBG)",
                original_value="5% to 10% of Contract Value",
                amended_value=f"{new_pbg}% of Contract Value",
                delta_summary=f"PBG Rate reduced to {new_pbg}%",
                severity="Moderate",
                action_required="Recalculate Bank Guarantee financing charges"
            )
        return None

    def _detect_delivery_change(self, text: str) -> Optional[DiffItem]:
        m = re.search(r"delivery\s+(?:period|time|schedule).*?(?:extended|revised|read)\s*(?:to)?[:\s\-]*(\d+)\s*(days|months|weeks)", text, re.IGNORECASE)
        if m:
            qty = m.group(1)
            unit = m.group(2)
            return DiffItem(
                parameter="Delivery / Completion Schedule",
                original_value="Standard timeline specified in RFP",
                amended_value=f"{qty} {unit.title()}",
                delta_summary=f"Execution window amended to {qty} {unit}",
                severity="Moderate",
                action_required="Align OEM dispatch schedule and logistics planning"
            )
        return None

    def _detect_clause_substitutions(self, text: str) -> List[DiffItem]:
        diffs = []
        # Match "Read 'XYZ' instead of 'ABC'"
        matches = re.findall(r"(?:read|substitute)\s+['\"]([^'\"]{4,80})['\"]\s+(?:instead of|in place of)\s+['\"]([^'\"]{4,80})['\"]", text, re.IGNORECASE)
        for new_val, old_val in matches[:3]:
            diffs.append(DiffItem(
                parameter="Specific Clause Amendment",
                original_value=old_val.strip(),
                amended_value=new_val.strip(),
                delta_summary="Textual specification substitution",
                severity="Moderate",
                action_required="Incorporate amended text in technical compliance sheet"
            ))
        return diffs

    def _normalize_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        cleaned = date_str.strip()[:10]
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        return None
