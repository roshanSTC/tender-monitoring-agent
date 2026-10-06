import io
import pandas as pd
from typing import List
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from core.models import TenderRecord

class ExportEngine:
    @staticmethod
    def generate_excel(tenders: List[TenderRecord]) -> bytes:
        """
        Generates an executive-ready Excel spreadsheet (.xlsx) with professional
        styling, status-based color highlights, and auto-sized columns.
        """
        rows = []
        for t in tenders:
            score = t.match_score
            val_cr = (t.estimated_value_inr / 10000000.0) if t.estimated_value_inr else None
            emd_lakh = (t.emd_amount_inr / 100000.0) if t.emd_amount_inr else None
            status_str = t.status.value if hasattr(t.status, "value") else str(t.status)
            portal_str = t.portal.value if hasattr(t.portal, "value") else str(t.portal)

            rows.append({
                "Tender ID": t.id,
                "Organization / Ministry": t.organization,
                "Portal": portal_str,
                "Match Score (%)": score,
                "Qualification Status": status_str,
                "Estimated Value (₹ Cr)": f"₹{val_cr:.2f} Cr" if val_cr else "Unspecified",
                "EMD (₹ Lakhs)": f"₹{emd_lakh:.2f} L" if emd_lakh else "Exempted",
                "Published Date": t.published_date,
                "Submission Due Date": t.due_date,
                "Tender Title / Scope": t.title,
                "Official Document Link": t.doc_url or "Available on Portal"
            })

        df = pd.DataFrame(rows)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            sheet_name = "Tender Radar Opportunities"
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]

            # Colors and styles
            header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid") # Dark Slate
            header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            
            qualified_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # Soft Green
            review_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")    # Soft Yellow
            disqual_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # Soft Red

            thin_border = Border(
                left=Side(style="thin", color="E5E7EB"),
                right=Side(style="thin", color="E5E7EB"),
                top=Side(style="thin", color="E5E7EB"),
                bottom=Side(style="thin", color="E5E7EB")
            )

            # Style header row
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            # Style data rows
            score_col_idx = 4
            for row_idx in range(2, len(df) + 2):
                score_cell = worksheet.cell(row=row_idx, column=score_col_idx)
                try:
                    score_val = int(score_cell.value)
                except (ValueError, TypeError):
                    score_val = 0

                row_fill = qualified_fill if score_val >= 75 else (review_fill if score_val >= 50 else disqual_fill)

                for col_idx in range(1, len(df.columns) + 1):
                    cell = worksheet.cell(row=row_idx, column=col_idx)
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")
                    if col_idx in [4, 5]: # Match score & status
                        cell.fill = row_fill
                        cell.alignment = Alignment(horizontal="center", vertical="center")

            # Auto-fit column widths
            for col in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = get_column_letter(col[0].column)
                worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 60)

        output.seek(0)
        return output.getvalue()

    @staticmethod
    def generate_csv(tenders: List[TenderRecord]) -> str:
        """
        Generates a clean comma-separated CSV string.
        """
        rows = []
        for t in tenders:
            val_cr = (t.estimated_value_inr / 10000000.0) if t.estimated_value_inr else 0.0
            emd_lakh = (t.emd_amount_inr / 100000.0) if t.emd_amount_inr else 0.0
            status_str = t.status.value if hasattr(t.status, "value") else str(t.status)
            portal_str = t.portal.value if hasattr(t.portal, "value") else str(t.portal)

            rows.append({
                "Tender ID": t.id,
                "Organization": t.organization,
                "Portal": portal_str,
                "Match Score (%)": t.match_score,
                "Status": status_str,
                "Estimated Value (₹ Cr)": round(val_cr, 2),
                "EMD (₹ Lakhs)": round(emd_lakh, 2),
                "Published Date": t.published_date,
                "Due Date": t.due_date,
                "Title": t.title,
                "Official URL": t.doc_url or ""
            })

        df = pd.DataFrame(rows)
        return df.to_csv(index=False)
