import os
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
