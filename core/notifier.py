import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from config.settings import (
    EMAIL_CONFIG_PATH,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_SENDER_NAME,
    SMTP_USE_TLS
)
from core.models import TenderRecord, Corrigendum
from core.logger import get_agent_logger

logger = get_agent_logger("Notifier")

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


class EmailNotifier:
    """
    Enterprise Email Alert Engine supporting TLS/SSL SMTP,
    rich HTML templates, and automated tender / corrigendum notifications.
    """

    @staticmethod
    def load_config() -> Dict[str, Any]:
        try:
            with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load email config from {EMAIL_CONFIG_PATH}: {e}")
            return {
                "enabled": False,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "use_tls": True,
                "sender_name": "TenderPulse Alerts",
                "recipient_emails": [],
                "min_alert_score": 75,
                "notify_on_corrigendum": True,
                "watchdog_interval_minutes": 180
            }

    @staticmethod
    def save_config(config_dict: Dict[str, Any]) -> bool:
        try:
            current = EmailNotifier.load_config()
            current.update(config_dict)
            with open(EMAIL_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
            logger.info("Email notification settings successfully updated.")
            return True
        except Exception as e:
            logger.error(f"Failed to save email config: {e}")
            return False

    @classmethod
    def send_email(
        cls,
        subject: str,
        html_body: str,
        recipients: Optional[List[str]] = None,
        attachment_bytes: Optional[bytes] = None,
        attachment_filename: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Dispatches email via static / configured SMTP server with optional file attachment.
        Returns (success_boolean, status_message).
        """
        cfg = cls.load_config()
        to_addrs = recipients if recipients else cfg.get("recipient_emails", [])
        
        if not to_addrs:
            return False, "No recipient email addresses specified."

        # Prefer static code/env variables if defined, else fallback to config file
        smtp_host = SMTP_HOST or cfg.get("smtp_host", "smtp.gmail.com")
        smtp_port = int(SMTP_PORT or cfg.get("smtp_port", 587))
        smtp_user = (SMTP_USER or cfg.get("smtp_user", "")).strip()
        smtp_pwd = (SMTP_PASSWORD or cfg.get("smtp_password", "")).strip()
        use_tls = SMTP_USE_TLS if SMTP_USE_TLS is not None else cfg.get("use_tls", True)
        sender_name = SMTP_SENDER_NAME or cfg.get("sender_name", "TenderPulse Alerts")

        if not smtp_user or not smtp_pwd:
            return False, "SMTP sender credentials not configured in settings.py or .env (SMTP_USER / SMTP_PASSWORD)."

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{smtp_user}>"
        msg["To"] = ", ".join(to_addrs)

        # Attach HTML body
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # Optional attachment (e.g. Excel export)
        if attachment_bytes and attachment_filename:
            part = MIMEApplication(attachment_bytes)
            part.add_header("Content-Disposition", "attachment", filename=attachment_filename)
            msg.attach(part)

        try:
            logger.info(f"Connecting to SMTP server [{smtp_host}:{smtp_port}]...")
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            if use_tls:
                server.starttls()
            server.login(smtp_user, smtp_pwd)
            server.send_message(msg)
            server.quit()
            logger.info(f"Dispatched email '{subject}' to {to_addrs}")
            return True, f"Successfully delivered email to {', '.join(to_addrs)}"

        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"SMTP Authentication failed (Check App Password or Username): {e}"
            logger.error(err_msg)
            return False, err_msg
        except Exception as e:
            err_msg = f"Network or SMTP error sending email: {str(e)}"
            logger.error(err_msg)
            return False, err_msg

    @classmethod
    def send_test_email(cls, recipient: str) -> Tuple[bool, str]:
        """
        Sends an instant diagnostic test email to verify SMTP credentials.
        """
        subject = "✅ [TenderPulse] Test Notification & SMTP Verification"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b;">
            <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden;">
                <div style="background-color: #0f172a; padding: 20px; text-align: center; color: #ffffff;">
                    <h2 style="margin: 0; font-size: 22px;">🛡️ TenderPulse Procurement Intelligence</h2>
                    <p style="margin: 5px 0 0; color: #94a3b8; font-size: 13px;">Autonomous Indian Tender Monitoring Agent</p>
                </div>
                <div style="padding: 24px;">
                    <div style="background-color: #dcfce7; border-left: 4px solid #16a34a; padding: 12px; margin-bottom: 20px; border-radius: 4px;">
                        <strong style="color: #15803d;">SMTP Verification Successful!</strong><br>
                        Your email notification pipeline is properly configured and operational.
                    </div>
                    <p>This automated test confirms that your SMTP credentials can successfully deliver high-priority procurement alerts directly to your inbox.</p>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px;">
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Dispatched At:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9;">{now_str}</td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Target Recipient:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9;">{recipient}</td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Status:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #16a34a;"><strong>Active & Ready</strong></td></tr>
                    </table>
                </div>
                <div style="background: #f1f5f9; padding: 14px; text-align: center; font-size: 12px; color: #64748b;">
                    Autonomous TenderPulse Agent • Local Indian Procurement Watchdog
                </div>
            </div>
        </body>
        </html>
        """
        return cls.send_email(subject, html_body, recipients=[recipient])

    @classmethod
    def send_tender_alert(cls, tender: TenderRecord, recipients: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        Dispatches a high-priority, formatted HTML alert for a newly detected qualified tender.
        """
        score = tender.match_score
        val_str = f"₹{tender.estimated_value_inr/10000000:.2f} Cr" if tender.estimated_value_inr else "Unspecified"
        emd_str = f"₹{tender.emd_amount_inr/100000:.2f} Lakhs" if tender.emd_amount_inr else "Exempted / Unspecified"
        portal_name = tender.portal.value if hasattr(tender.portal, "value") else str(tender.portal)

        subject = f"🚨 [{score}% Match Qualified] {tender.organization}: {tender.id[:45]}"

        summary_text = tender.analysis_report.summary if tender.analysis_report else tender.title
        qual_status = tender.analysis_report.qualification_status if tender.analysis_report else "Qualified"

        badge_bg = "#dcfce7" if score >= 75 else "#fef9c3"
        badge_color = "#15803d" if score >= 75 else "#854d0e"

        # Build eligibility rows
        eligibility_rows = ""
        if tender.analysis_report and tender.analysis_report.eligibility_breakdown:
            for item in tender.analysis_report.eligibility_breakdown:
                icon = "✅" if item.is_eligible else "❌"
                eligibility_rows += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{icon} <strong>{item.parameter}</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; color: #475569;">Req: {item.required_value}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; color: #15803d;">{item.remarks}</td>
                </tr>
                """

        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b; margin: 0;">
            <div style="max-width: 650px; margin: auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <div style="background-color: #0f172a; padding: 20px; text-align: left; color: #ffffff;">
                    <div style="float: right; background-color: {badge_bg}; color: {badge_color}; font-weight: bold; padding: 6px 14px; border-radius: 20px; font-size: 14px;">
                        {score}% MATCH • {qual_status.upper()}
                    </div>
                    <h2 style="margin: 0; font-size: 20px;">🛡️ High-Match Tender Detected</h2>
                    <p style="margin: 4px 0 0; color: #94a3b8; font-size: 13px;">{tender.organization}</p>
                </div>
                
                <div style="padding: 24px;">
                    <h3 style="margin-top: 0; color: #0f172a; font-size: 17px; line-height: 1.4;">{tender.title}</h3>

                    <table style="width: 100%; border-collapse: collapse; margin: 18px 0; font-size: 14px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0;">
                        <tr><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #64748b; width: 35%;"><strong>Tender Ref No:</strong></td><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0;"><code>{tender.id}</code></td></tr>
                        <tr><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #64748b;"><strong>Procuring Authority:</strong></td><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0;">{tender.organization}</td></tr>
                        <tr><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #64748b;"><strong>Source Portal:</strong></td><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0;">{portal_name}</td></tr>
                        <tr><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #64748b;"><strong>Estimated Value:</strong></td><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #0f172a;">{val_str}</td></tr>
                        <tr><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0; color: #64748b;"><strong>EMD Amount:</strong></td><td style="padding: 10px 14px; border-bottom: 1px solid #e2e8f0;">{emd_str}</td></tr>
                        <tr><td style="padding: 10px 14px; color: #64748b;"><strong>Submission Due Date:</strong></td><td style="padding: 10px 14px; font-weight: bold; color: #dc2626;">{tender.due_date}</td></tr>
                    </table>

                    <h4 style="margin-bottom: 8px; color: #334155;">📝 Executive Evaluation Brief:</h4>
                    <p style="background: #f1f5f9; padding: 12px; border-radius: 6px; font-size: 13.5px; line-height: 1.5; color: #334155;">
                        {summary_text}
                    </p>

                    {f'<h4 style="margin-bottom: 8px; color: #334155;">⚖️ Criteria Compliance Matrix:</h4><table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px;">{eligibility_rows}</table>' if eligibility_rows else ''}

                    <div style="margin-top: 25px; text-align: center;">
                        <a href="{tender.doc_url or '#'}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; font-size: 14px;">
                            📄 Open Official Tender Document PDF
                        </a>
                    </div>
                </div>

                <div style="background: #f1f5f9; padding: 14px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0;">
                    Dispatched automatically by TenderPulse Autonomous Watchdog • Local Heuristic Engine
                </div>
            </div>
        </body>
        </html>
        """
        return cls.send_email(subject, html_body, recipients=recipients)

    @classmethod
    def send_corrigendum_alert(cls, tender: TenderRecord, corrigendum: Corrigendum, recipients: Optional[List[str]] = None) -> Tuple[bool, str]:
        """
        Dispatches an urgent alert when a corrigendum or addendum is published.
        """
        subject = f"⚠️ [CORRIGENDUM ISSUED] {tender.organization} - Ref: {tender.id[:40]}"

        # Build side-by-side diff table if available
        diff_table_html = ""
        if corrigendum.diff_items:
            diff_table_html = """
            <h4 style="margin: 20px 0 8px; color: #1e293b;">🔍 Side-by-Side Differential Matrix:</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 15px;">
                <tr style="background: #f1f5f9; text-align: left;">
                    <th style="padding: 6px; border: 1px solid #e2e8f0;">Parameter</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0;">Original NIT</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0;">Amended Term</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0;">Delta / Impact</th>
                </tr>
            """
            for di in corrigendum.diff_items:
                d_dict = di if isinstance(di, dict) else di.model_dump()
                diff_table_html += f"""
                <tr>
                    <td style="padding: 6px; border: 1px solid #e2e8f0;"><strong>{d_dict.get('parameter')}</strong></td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; color: #dc2626;">{d_dict.get('original_value')}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; color: #16a34a;"><strong>{d_dict.get('amended_value')}</strong></td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0;">{d_dict.get('delta_summary')}</td>
                </tr>
                """
            diff_table_html += "</table>"

        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #1e293b;">
            <div style="max-width: 650px; margin: auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden;">
                <div style="background-color: #b91c1c; padding: 20px; text-align: center; color: #ffffff;">
                    <h2 style="margin: 0; font-size: 20px;">⚠️ Critical Corrigendum / Addendum Published</h2>
                    <p style="margin: 5px 0 0; color: #fecaca; font-size: 13px;">Immediate review recommended for active tender</p>
                </div>
                <div style="padding: 24px;">
                    <p><strong>Tender Title:</strong> {tender.title}</p>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px;">
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Tender Ref:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9;"><code>{tender.id}</code></td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Authority:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9;">{tender.organization}</td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Published Date:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9;">{corrigendum.published_date}</td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Amended Elements:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #dc2626;"><strong>{', '.join(corrigendum.amended_fields) if corrigendum.amended_fields else 'Terms & Dates'}</strong></td></tr>
                        <tr><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #64748b;"><strong>Impact Verdict:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #f1f5f9; color: #16a34a;"><strong>{corrigendum.qualification_impact or 'Terms amended'}</strong></td></tr>
                    </table>
                    
                    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 14px; margin-top: 20px; border-radius: 4px; font-size: 13.5px;">
                        <strong>Corrigendum Description:</strong><br>
                        {corrigendum.description}
                    </div>

                    {diff_table_html}

                    <div style="margin-top: 25px; text-align: center;">
                        <a href="{corrigendum.document_url or tender.doc_url or '#'}" style="display: inline-block; background-color: #0f172a; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-size: 13px;">
                            📄 Download Corrigendum Notice
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return cls.send_email(subject, html_body, recipients=recipients)
