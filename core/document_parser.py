import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from pypdf import PdfReader
from core.logger import get_agent_logger, ScrapingAuditLogger

logger = get_agent_logger("DocumentParser")

class DocumentParser:
    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> str:
        if not os.path.exists(pdf_path):
            logger.error(f"Target document not found at: {pdf_path}")
            raise FileNotFoundError(f"File not found: {pdf_path}")

        file_size = os.path.getsize(pdf_path)
        logger.info(f"Opening PDF document [{os.path.basename(pdf_path)}] ({file_size / 1024:.1f} KB)")
        start_time = time.time()

        extracted_text = []
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    extracted_text.append(f"--- PAGE {i+1} ---\n{page_text}")
            
            elapsed_ms = (time.time() - start_time) * 1000
            total_chars = sum(len(p) for p in extracted_text)
            logger.info(f"Successfully parsed {num_pages} pages ({total_chars} chars) in {elapsed_ms:.2f}ms")

            ScrapingAuditLogger.record_event(
                action="DOCUMENT_PARSED",
                target_portal="Local Upload / Storage",
                target_url=pdf_path,
                response_time_ms=elapsed_ms,
                payload_bytes=file_size,
                details=f"Extracted {num_pages} pages, {total_chars} characters"
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Error extracting PDF [{pdf_path}]: {str(e)}")
            ScrapingAuditLogger.record_event(
                action="DOCUMENT_PARSE_ERROR",
                target_portal="Local Upload / Storage",
                target_url=pdf_path,
                response_time_ms=elapsed_ms,
                error=str(e)
            )
            return f"Error extracting PDF: {str(e)}"

        return "\n\n".join(extracted_text)

    @staticmethod
    def extract_key_sections(full_text: str) -> Dict[str, str]:
        sections = {
            "scope_of_work": "",
            "eligibility_criteria": "",
            "financial_terms": "",
            "penalties": "",
            "timeline": ""
        }
        lines = full_text.splitlines()
        current_section = None
        buffer = []

        keywords_map = {
            "scope of work": "scope_of_work",
            "scope of contract": "scope_of_work",
            "technical specifications": "scope_of_work",
            "eligibility criteria": "eligibility_criteria",
            "qualification criteria": "eligibility_criteria",
            "pre-qualification": "eligibility_criteria",
            "minimum eligibility": "eligibility_criteria",
            "earnest money deposit": "financial_terms",
            "emd": "financial_terms",
            "payment terms": "financial_terms",
            "turnover": "financial_terms",
            "liquidated damages": "penalties",
            "penalty clause": "penalties",
            "delivery schedule": "timeline",
            "completion period": "timeline",
            "submission deadline": "timeline"
        }

        for line in lines:
            line_lower = line.strip().lower()
            matched = False
            for kw, sec_key in keywords_map.items():
                if kw in line_lower and len(line_lower) < 60:
                    if current_section and buffer:
                        sections[current_section] = "\n".join(buffer[-20:])
                    current_section = sec_key
                    buffer = [line]
                    matched = True
                    break

            if not matched and current_section:
                buffer.append(line)

        if current_section and buffer:
            sections[current_section] = "\n".join(buffer[-20:])

        return sections

    @staticmethod
    def extract_required_submissions(full_text: str) -> List[str]:
        """
        Dynamically extracts mandatory bid submission documents, forms, checklists,
        and packet exhibits directly from raw tender document text.
        """
        if not full_text or len(full_text.strip()) < 50:
            return []

        # Clean unprintable or non-standard characters from text
        normalized_text = full_text.replace("\ufffd", "-").replace("\u2013", "-").replace("\u2014", "-")
        submissions = []

        # Strategy 1: FORM 6 / Check-list for Bidders (Table format in BNPM, SPM, modern CPPP/GTE tenders)
        checklist_match = re.search(
            r"FORM\s*6\s*:\s*CHECK-?LIST\s+FOR\s+BIDDERS.*?(?=(?:FORMATS|\n\s*Section\s+VIII|\n\s*Duly authorized to sign|\Z))",
            normalized_text,
            re.IGNORECASE | re.DOTALL
        )
        if checklist_match:
            block = checklist_match.group(0)
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            curr_num = ""
            curr_text = ""
            for line in lines:
                if any(k in line for k in ["Note to Bidders", "Sr Documents submitted", "Page 2", "Page 3", "Page 4 of"]):
                    continue
                if re.search(r"(Signature with date|Duly authorized to sign|Name and designation)", line, re.IGNORECASE):
                    if curr_text:
                        submissions.append(f"{curr_num} {curr_text}".strip())
                        curr_num, curr_text = "", ""
                    break
                m = re.match(r"^(\d+(?:\.[a-z0-9]+)?|[a-z]\))\s*(.*)", line, re.IGNORECASE)
                if m:
                    if curr_text:
                        submissions.append(f"{curr_num} {curr_text}".strip())
                    curr_num = m.group(1)
                    curr_text = m.group(2).strip()
                elif re.match(r"^\d+\.$", line):
                    if curr_text:
                        submissions.append(f"{curr_num} {curr_text}".strip())
                    curr_num = line
                    curr_text = ""
                elif curr_num:
                    if not re.match(r"^(Yes|No|NA|FORM\s*6)", line, re.IGNORECASE):
                        curr_text += " " + line
            if curr_text:
                submissions.append(f"{curr_num} {curr_text}".strip())

        if len(submissions) >= 5:
            cleaned = []
            for s in submissions:
                sc = re.sub(r"---\s*PAGE\s*\d+\s*---", "", s, flags=re.IGNORECASE)
                sc = re.sub(r"Page\s+\d+\s+of\s+\d+", "", sc, flags=re.IGNORECASE)
                sc = re.sub(r"\s+", " ", sc).strip()
                sc = re.sub(r"^(\d+)\s*\.\s*", r"\1. ", sc)
                sc = re.sub(r"[\s\.\-\u2026]+$", "", sc)
                if len(sc) > 6 and not sc.lower().startswith("any other requirements"):
                    cleaned.append(sc)
                elif sc.lower().startswith("any other requirements"):
                    cleaned.append("Other statutory / technical documents stipulated in TIS / ITB")
            if cleaned:
                return cleaned

        # Strategy 2: SIT-3 / Submission of Tender / Documents Comprising the Bid (SPMCIL, ISP Nashik, CNP)
        sit_match = re.search(
            r"(?:SIT-3\s*:?\s*Submission of Tender|9\.2\s+Documents comprising the bid).*?(?=(?:SIT-4|SIT-5|9\.3\s+Bid Validity|\n\s*Section\s+IV|\Z))",
            normalized_text,
            re.IGNORECASE | re.DOTALL
        )
        if sit_match:
            block = sit_match.group(0)
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            curr_item = ""
            for line in lines:
                if "Page " in line or "Tender Number:" in line:
                    continue
                m = re.match(r"^(?:Part\s*[-–]?[I|V|X]+:?|[I|V|X]+\.|\d+\)|\d+\.|\([a-z]\))\s*(.*)", line)
                if m:
                    if curr_item:
                        submissions.append(curr_item)
                    curr_item = line
                elif curr_item:
                    curr_item += " " + line
            if curr_item:
                submissions.append(curr_item)

        if len(submissions) >= 4:
            cleaned = [re.sub(r"\s+", " ", s).strip() for s in submissions if len(s) > 10]
            if cleaned:
                return cleaned

        # Strategy 3: Forms and Schedules enumerated in Tender Body
        forms = re.findall(r"(Form\s+\d+(?:\.\d+)?\s*[:\-–]?\s*[A-Za-z\s&,\(\)/]+?)(?=\s*(?:\d+\s*[–-]\s*\d+|\n|$))", normalized_text, re.IGNORECASE)
        if forms and len(forms) >= 5:
            seen = set()
            clean_forms = []
            for f in forms:
                f_clean = re.sub(r"\s+", " ", f).strip()
                if f_clean.lower() not in seen and 8 < len(f_clean) < 90:
                    seen.add(f_clean.lower())
                    clean_forms.append(f_clean)
            if len(clean_forms) >= 4:
                return clean_forms

        return []

