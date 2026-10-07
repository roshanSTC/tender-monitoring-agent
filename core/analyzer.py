import re
import json
from typing import Dict, Any, List, Optional
from config.settings import COMPANY_PROFILE_PATH
from core.models import TenderAnalysisReport, EligibilityItem
from core.logger import get_agent_logger
from core.document_parser import DocumentParser

logger = get_agent_logger("Analyzer")

class TenderAnalyzer:
    def __init__(self, company_profile_path=COMPANY_PROFILE_PATH):
        self.company_profile = self._load_profile(company_profile_path)

    def _load_profile(self, path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load custom company profile from {path}: {e}. Using defaults.")
            return {
                "company_name": "Apex Infotech & Engineering Solutions Pvt Ltd",
                "financials": {"annual_turnover_inr_cr": 25.0, "net_worth_inr_cr": 8.5, "max_emd_capacity_inr_lakhs": 50.0},
                "certifications": ["ISO 9001:2015", "ISO 27001:2013", "ISO 20000-1", "CMMI Level 3"],
                "experience": {"years_in_business": 8, "completed_govt_projects": 14, "largest_single_order_inr_cr": 12.0}
            }

    def analyze_tender(self, tender_title: str, tender_text: str, metadata: Optional[Dict[str, Any]] = None) -> TenderAnalysisReport:
        metadata = metadata or {}
        text_lower = tender_text.lower()
        title_lower = tender_title.lower()
        org_name = metadata.get("organization", "Procuring Authority")
        logger.info(f"Evaluating tender '{tender_title}' from [{org_name}]")

        co_turnover_cr = self.company_profile.get("financials", {}).get("annual_turnover_inr_cr", 25.0)
        req_turnover_cr = self._extract_turnover_req(tender_text, metadata.get("estimated_value_inr"))
        
        turnover_eligible = co_turnover_cr >= req_turnover_cr
        turnover_item = EligibilityItem(
            parameter="Annual Turnover Requirement",
            required_value=f"₹{req_turnover_cr:.2f} Cr" if req_turnover_cr > 0 else "Not explicitly specified",
            company_value=f"₹{co_turnover_cr:.2f} Cr (Average 3 Years)",
            is_eligible=turnover_eligible,
            risk_level="High" if not turnover_eligible else "Low",
            remarks="Meets financial criterion" if turnover_eligible else "Company turnover below tender threshold"
        )

        co_max_emd_lakhs = self.company_profile.get("financials", {}).get("max_emd_capacity_inr_lakhs", 50.0)
        emd_inr = metadata.get("emd_amount_inr") or self._extract_emd(tender_text)
        emd_lakhs = (emd_inr / 100000.0) if emd_inr else 0.0

        emd_eligible = (emd_lakhs <= co_max_emd_lakhs)
        emd_item = EligibilityItem(
            parameter="Earnest Money Deposit (EMD)",
            required_value=f"₹{emd_lakhs:.2f} Lakhs" if emd_lakhs > 0 else "Exempted / Not specified",
            company_value=f"Max ₹{co_max_emd_lakhs:.2f} Lakhs capacity",
            is_eligible=emd_eligible,
            risk_level="Medium" if not emd_eligible else "Low",
            remarks="Within approved bank guarantee/EMD budget" if emd_eligible else "Exceeds approved EMD allocation"
        )

        co_certs = [c.lower() for c in self.company_profile.get("certifications", [])]
        found_certs = []
        missing_certs = []
        target_certs = ["iso 9001", "iso 27001", "iso 20000", "cmmi", "bis", "stqc"]
        
        for cert in target_certs:
            if re.search(r"\b" + re.escape(cert) + r"\b", text_lower):
                matched = any(cert in c for c in co_certs)
                if matched:
                    found_certs.append(cert.upper())
                else:
                    missing_certs.append(cert.upper())

        certs_eligible = len(missing_certs) == 0
        cert_remarks = f"Holds required certificates: {', '.join(found_certs)}" if certs_eligible else f"Missing required certification(s): {', '.join(missing_certs)}"
        cert_item = EligibilityItem(
            parameter="Required Certifications",
            required_value=", ".join(found_certs + missing_certs) if (found_certs or missing_certs) else "Standard ISO preferred",
            company_value=", ".join(self.company_profile.get("certifications", [])),
            is_eligible=certs_eligible,
            risk_level="High" if not certs_eligible else "Low",
            remarks=cert_remarks
        )

        co_exp_years = self.company_profile.get("experience", {}).get("years_in_business", 5)
        req_exp_years = 3
        if "5 years" in text_lower or "five years" in text_lower:
            req_exp_years = 5
        elif "7 years" in text_lower:
            req_exp_years = 7

        exp_eligible = co_exp_years >= req_exp_years
        exp_item = EligibilityItem(
            parameter="Past Operating Experience",
            required_value=f"Minimum {req_exp_years} years in similar domain",
            company_value=f"{co_exp_years} years active operations",
            is_eligible=exp_eligible,
            risk_level="Low" if exp_eligible else "High",
            remarks="Past project credentials qualify" if exp_eligible else "Insufficient years in business"
        )

        penalties_found = []
        if "liquidated damages" in text_lower or "ld clause" in text_lower:
            penalties_found.append("Liquidated damages (LD) of 0.5% per week up to 10% maximum.")
        if "blacklisting" in text_lower or "debarment" in text_lower:
            penalties_found.append("Standard debarment/blacklisting clause for default.")
        if "bank guarantee" in text_lower or "performance security" in text_lower:
            penalties_found.append("Performance Bank Guarantee (PBG) of 3% to 5% required within 15 days of LoA.")
        if not penalties_found:
            penalties_found.append("Standard portal terms and conditions applicable.")

        # Dynamically extract required submissions and forms from the uploaded tender text
        dynamic_submissions = DocumentParser.extract_required_submissions(tender_text)
        if dynamic_submissions and len(dynamic_submissions) >= 3:
            required_docs = dynamic_submissions
            logger.info(f"Dynamically extracted {len(required_docs)} tender submissions directly from document.")
        else:
            required_docs = [
                "GST Registration Certificate",
                "PAN Card & Incorporation Certificate",
                "Audited Balance Sheets (Last 3 FY) with CA UDIN",
                "EMD Payment Receipt / Bank Guarantee or MSME Exemption Certificate",
                "OEM Authorization Form (MAF) if bidding as reseller",
                "Non-Blacklisting Undertaking on Stamp Paper"
            ]
            if found_certs:
                required_docs.append(f"Valid Certificate Copies ({', '.join(found_certs)})")
            logger.info(f"Using default statutory checklist ({len(required_docs)} exhibits) as fallback.")

        items = [turnover_item, emd_item, cert_item, exp_item]
        passed_count = sum(1 for it in items if it.is_eligible)
        base_score = int((passed_count / len(items)) * 80)
        
        keywords = self.company_profile.get("keywords", [])
        keyword_hits = sum(1 for kw in keywords if kw in text_lower or kw in title_lower)
        relevance_boost = min(keyword_hits * 4, 20)
        final_score = min(base_score + relevance_boost, 100)

        if final_score >= 75 and turnover_eligible and certs_eligible:
            qual_status = "Qualified"
        elif final_score >= 50:
            qual_status = "Conditional (Review Needed)"
        else:
            qual_status = "Disqualified"

        logger.info(f"Evaluation complete for '{tender_title}': Score={final_score}/100, Verdict={qual_status}")

        org_name = metadata.get("organization", "Procuring Authority")
        est_val_str = f"estimated at ₹{metadata.get('estimated_value_inr')/10000000:.2f} Cr" if metadata.get('estimated_value_inr') else "with unpriced schedule"
        summary_text = (
            f"This tender issued by {org_name} covers {tender_title}, {est_val_str}. "
            f"Automated evaluation against company credentials yields a match score of {final_score}/100 ({qual_status}). "
            f"{'All core financial and certification criteria are met.' if qual_status == 'Qualified' else 'Crucial qualification items require consortium or management review.'} "
            f"Submission requires {len(required_docs)} mandatory compliance exhibits."
        )

        return TenderAnalysisReport(
            summary=summary_text,
            overall_match_score=final_score,
            qualification_status=qual_status,
            estimated_tender_value_inr=metadata.get("estimated_value_inr"),
            emd_amount_inr=emd_inr,
            submission_deadline=metadata.get("due_date", "Refer to NIT schedule"),
            delivery_period="90 - 180 Days" if "month" in text_lower or "day" in text_lower else "As per tender clause",
            penalties_and_risks=penalties_found,
            required_documents=required_docs,
            eligibility_breakdown=items
        )

    def _extract_turnover_req(self, text: str, est_val: Optional[float]) -> float:
        m = re.search(r"turnover.*?(\d+(?:,\d+)*(?:\.\d+)?)\s*(crore|cr|lakh|lacs)", text, re.IGNORECASE)
        if m:
            val_str = m.group(1).replace(",", "")
            val = float(val_str)
            unit = m.group(2).lower()
            return val if "cr" in unit or "crore" in unit else (val / 100.0)
        if est_val:
            return round((est_val * 0.40) / 10000000.0, 2)
        return 5.0

    def _extract_emd(self, text: str) -> Optional[float]:
        m = re.search(
            r"(?:earnest\s+money\s+deposit|emd|bid\s+security)(?:\s*(?:amount|is|of))?[:\s\-–]*(?:inr|rs\.?|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
            text,
            re.IGNORECASE
        )
        if m:
            val_str = m.group(1).replace(",", "")
            try:
                val = float(val_str)
                if val > 1000:
                    return val
            except ValueError:
                pass
        return None
