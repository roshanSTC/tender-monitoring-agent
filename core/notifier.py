import json
from typing import Dict, Any, Optional
from core.models import TenderRecord, Corrigendum

class TenderNotifier:
    @staticmethod
    def format_tender_alert(tender: TenderRecord) -> str:
        val_str = f"₹{tender.estimated_value_inr/10000000:.2f} Cr" if tender.estimated_value_inr else "Not Disclosed"
        emd_str = f"₹{tender.emd_amount_inr/100000:.2f} Lakhs" if tender.emd_amount_inr else "Exempted"

        msg = (
            f"🚨 *NEW HIGH-MATCH TENDER DETECTED ({tender.match_score}% Match)*\n\n"
            f"📌 *Tender Ref:* {tender.id}\n"
            f"🏛 *Authority:* {tender.organization}\n"
            f"🌐 *Portal:* {tender.portal.value if hasattr(tender.portal, 'value') else tender.portal}\n"
            f"📋 *Scope:* {tender.title}\n"
            f"💰 *Estimated Value:* {val_str} | *EMD:* {emd_str}\n"
            f"⏰ *Due Date:* {tender.due_date}\n\n"
            f"📊 *Agent Qualification:* {tender.analysis_report.qualification_status if tender.analysis_report else 'Pending'}\n"
            f"📝 *Summary:* {tender.analysis_report.summary if tender.analysis_report else 'No summary available.'}\n"
        )
        return msg

    @staticmethod
    def format_corrigendum_alert(tender: TenderRecord, corrigendum: Corrigendum) -> str:
        msg = (
            f"⚠️ *CRITICAL CORRIGENDUM ISSUED*\n\n"
            f"📌 *Tender Ref:* {tender.id} ({tender.title})\n"
            f"🏛 *Authority:* {tender.organization}\n"
            f"📅 *Corrigendum Published:* {corrigendum.published_date}\n"
            f"📝 *Details:* {corrigendum.description}\n"
            f"⚡ *Amended Fields:* {', '.join(corrigendum.amended_fields)}\n"
        )
        return msg
