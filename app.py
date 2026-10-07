import core.win_patch  # Suppress harmless Windows socket WinError 10054
import streamlit as st
import os
import re
import json
from datetime import datetime
import pandas as pd
from config.settings import COMPANY_PROFILE_PATH, TENDERS_DIR, LOG_FILE_PATH, AUDIT_LOG_PATH
from core.database import TenderDatabase
from core.scraper import IndianTenderScraper
from core.analyzer import TenderAnalyzer
from core.document_parser import DocumentParser
from core.notifier import TenderNotifier, EmailNotifier
from core.models import TenderRecord, BidDecisionStatus, TenderSource
from core.logger import get_agent_logger, ScrapingAuditLogger
from core.export_engine import ExportEngine
from core.bid_pack_generator import BidPackGenerator
from core.watchdog import AutonomousWatchdogService
from core.diff_engine import CorrigendumDiffEngine

logger = get_agent_logger("Dashboard")
watchdog = AutonomousWatchdogService.get_instance()

st.set_page_config(
    page_title="TenderPulse | Autonomous Tender Monitoring Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown('''
<style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .badge-qualified {
        background-color: #dcfce7;
        color: #15803d;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
    }
    .badge-review {
        background-color: #fef9c3;
        color: #a16207;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
    }
    .badge-disqualified {
        background-color: #fee2e2;
        color: #b91c1c;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
    }
</style>
''', unsafe_allow_html=True)

if "db" not in st.session_state:
    db = TenderDatabase()
    st.session_state.db = db
    existing = db.get_all_tenders()
    if not existing:
        scraper = IndianTenderScraper()
        initial_tenders = scraper.fetch_curated_indian_tenders()
        for t in initial_tenders:
            db.save_tender(t)

db: TenderDatabase = st.session_state.db
analyzer = TenderAnalyzer()
diff_engine = CorrigendumDiffEngine(analyzer=analyzer)

with st.sidebar:
    st.title("🛡️ TenderPulse Agent")
    st.caption("AI-Powered Procurement Intelligence for GeM, CPPP & SPMCIL")
    st.markdown("---")

    st.subheader("🧭 Screen Navigation")
    selected_view = st.radio(
        "Select Screen:",
        [
            "📡 Live Tender Radar",
            "📄 Upload & Analyze Custom PDF",
            "💼 Bid Pipeline & Corrigendums",
            "🔔 Email Alerts & Autonomous Watchdog",
            "⚙️ Company Profile Config",
            "📋 Live Scraping Logs & Audit Trail"
        ],
        index=0
    )
    st.markdown("---")

    try:
        with open(COMPANY_PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)
        st.subheader("🏢 Active Bidder Profile")
        st.write(f"**{profile.get('company_name', 'Company')}**")
        st.write(f"Turnover: **₹{profile.get('financials', {}).get('annual_turnover_inr_cr', 0)} Cr**")
        st.write(f"Max EMD: **₹{profile.get('financials', {}).get('max_emd_capacity_inr_lakhs', 0)} Lakhs**")
        st.write(f"Certs: {', '.join(profile.get('certifications', [])[:3])}")
    except Exception:
        profile = {}

    st.markdown("---")
    st.subheader("🌐 Monitored Portals")
    st.markdown("✅ **GeM** (Government e-Marketplace)")
    st.markdown("✅ **CPPP** (Central Public Procurement Portal)")
    st.markdown("✅ **SPMCIL Mints & Presses (All 9 Units)**")

    st.markdown("---")
    if st.button("🔄 Refresh & Sync Live Feeds", width="stretch"):
        scraper = IndianTenderScraper(analyzer=analyzer)
        new_items = scraper.fetch_curated_indian_tenders()
        for item in new_items:
            db.save_tender(item)
        st.toast("Synchronized live tenders across all portals!", icon="✅")
        st.rerun()

stats = db.get_stats()
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Monitored Bids", f"{stats['total_tenders']}")
with col2:
    st.metric("High Match (≥70%)", f"{stats['high_match_count']}", delta="Qualified")
with col3:
    st.metric("Pursuing in Pipeline", f"{stats['pursuing_count']}")
with col4:
    pipeline_val_cr = stats['pursuing_value_inr'] / 10000000.0
    st.metric("Pipeline Value", f"₹{pipeline_val_cr:.2f} Cr")

st.markdown("---")

# ----------------- SCREEN ROUTING -----------------
if selected_view == "📡 Live Tender Radar":
    f_col1, f_col2, f_col3, f_col4 = st.columns([1.2, 1.4, 1.5, 2.0])
    all_tenders = db.get_all_tenders()
    distinct_portals = sorted(list(set(t.portal.value if hasattr(t.portal, 'value') else str(t.portal) for t in all_tenders)))
    
    with f_col1:
        portal_filter = st.selectbox("Portal Filter", ["All Portals"] + distinct_portals)
    with f_col2:
        status_filter = st.selectbox("Match Status", ["All Statuses", "High Match (Qualified)", "Review Needed", "Disqualified", "Pursuing Bid"])
    with f_col3:
        sort_by = st.selectbox("Sort Order", ["Match Score (Highest First)", "Due Date (Earliest First)", "Due Date (Latest First)"])
    with f_col4:
        search_query = st.text_input("🔍 Search keyword, department or tender ID", "")

    filtered_tenders = []
    for t in all_tenders:
        portal_str = t.portal.value if hasattr(t.portal, 'value') else t.portal
        status_str = t.status.value if hasattr(t.status, 'value') else t.status

        if portal_filter != "All Portals" and portal_str != portal_filter:
            continue
        if status_filter != "All Statuses" and status_str != status_filter:
            continue
        if search_query:
            terms = search_query.strip().lower().split()
            haystack = f"{t.title} {t.organization} {t.id} {t.category}".lower()
            if not all(term in haystack for term in terms):
                continue
        filtered_tenders.append(t)

    # Sort filtered results
    if sort_by == "Match Score (Highest First)":
        filtered_tenders.sort(key=lambda x: (x.match_score, x.due_date), reverse=True)
    elif sort_by == "Due Date (Earliest First)":
        filtered_tenders.sort(key=lambda x: x.due_date)
    elif sort_by == "Due Date (Latest First)":
        filtered_tenders.sort(key=lambda x: x.due_date, reverse=True)

    if not filtered_tenders:
        st.info("No tenders match the specified filter.")
    else:
        page_size = 15
        total_pages = max(1, (len(filtered_tenders) + page_size - 1) // page_size)
        
        pag_col1, pag_col2, pag_col3, pag_col4 = st.columns([1.2, 3.2, 1.4, 1.4])
        with pag_col1:
            page_num = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
        with pag_col2:
            st.caption(f"Showing page **{page_num} of {total_pages}** ({len(filtered_tenders)} matching bids)")
        with pag_col3:
            excel_bytes = ExportEngine.generate_excel(filtered_tenders)
            st.download_button(
                label="📊 Export Excel",
                data=excel_bytes,
                file_name=f"Tender_Radar_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with pag_col4:
            csv_str = ExportEngine.generate_csv(filtered_tenders)
            st.download_button(
                label="📄 Export CSV",
                data=csv_str,
                file_name=f"Tender_Radar_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        start_idx = (page_num - 1) * page_size
        page_tenders = filtered_tenders[start_idx : start_idx + page_size]

        for tender in page_tenders:
            score = tender.match_score
            val_cr = (tender.estimated_value_inr / 10000000.0) if tender.estimated_value_inr else 0.0
            emd_lakh = (tender.emd_amount_inr / 100000.0) if tender.emd_amount_inr else 0.0
            portal_val = tender.portal.value if hasattr(tender.portal, 'value') else tender.portal
            status_val = tender.status.value if hasattr(tender.status, 'value') else tender.status

            with st.expander(f"**[{score}% Match]** {tender.title} — *{tender.organization}* | Due: {tender.due_date}", expanded=False):
                t_col1, t_col2, t_col3, t_col4 = st.columns(4)
                t_col1.write(f"**Tender ID:** `{tender.id}`")
                t_col2.write(f"**Portal:** {portal_val}")
                t_col3.write(f"**Value:** ₹{val_cr:.2f} Cr" if val_cr > 0 else "**Value:** Unspecified")
                t_col4.write(f"**EMD:** ₹{emd_lakh:.2f} Lakhs" if emd_lakh > 0 else "**EMD:** Exempted")

                if tender.doc_path:
                    import os
                    st.caption(f"📁 **Attached Document:** `{os.path.basename(tender.doc_path)}`")
                elif tender.doc_url:
                    st.caption(f"🔗 [Download Original Tender PDF]({tender.doc_url})")

                badge_class = "badge-qualified" if score >= 75 else ("badge-review" if score >= 50 else "badge-disqualified")
                st.markdown(f"**Qualification Status:** <span class='{badge_class}'>{status_val}</span>", unsafe_allow_html=True)
                st.progress(score / 100.0)

                if tender.analysis_report:
                    rep = tender.analysis_report
                    st.markdown("#### 📝 Executive Brief & Scope")
                    st.write(rep.summary)

                    e_col1, e_col2 = st.columns([1.5, 1])
                    with e_col1:
                        st.markdown("#### ⚖️ Eligibility Criteria Assessment")
                        for item in rep.eligibility_breakdown:
                            icon = "✅" if item.is_eligible else "❌"
                            st.markdown(f"**{icon} {item.parameter}**")
                            st.caption(f"Required: `{item.required_value}` | Company: `{item.company_value}` — *{item.remarks}*")

                    with e_col2:
                        st.markdown("#### 📋 Required Submissions")
                        for doc in rep.required_documents:
                            st.write(f"• {doc}")

                        if rep.penalties_and_risks:
                            st.markdown("#### ⚠️ Identified Clauses & Penalties")
                            for risk in rep.penalties_and_risks:
                                st.caption(f"⚠️ {risk}")

                if tender.corrigendums:
                    st.warning(f"📢 **{len(tender.corrigendums)} Corrigendum / Addendum Published:**")
                    for c in tender.corrigendums:
                        c_dict = c if isinstance(c, dict) else c.model_dump()
                        st.write(f"• **{c_dict.get('corrigendum_id')}** ({c_dict.get('published_date')}): {c_dict.get('description')}")

                st.markdown("---")
                btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1.2, 1.2, 1.2, 2.4])
                
                with btn_col1:
                    if st.button("🚀 Pursue Bid", key=f"pursue_{tender.id}"):
                        db.update_status(tender.id, BidDecisionStatus.PURSUING)
                        st.success("Tender moved to active Bidding Pipeline!")
                        st.rerun()

                with btn_col2:
                    if st.button("🔍 Mark Review", key=f"review_{tender.id}"):
                        db.update_status(tender.id, BidDecisionStatus.REVIEW_NEEDED)
                        st.rerun()

                with btn_col3:
                    if st.button("❌ Drop Tender", key=f"drop_{tender.id}"):
                        db.update_status(tender.id, BidDecisionStatus.DROPPED)
                        st.rerun()

                with btn_col4:
                    if st.button("🔔 Send Sample Alert (Slack/WhatsApp)", key=f"alert_{tender.id}"):
                        alert_text = TenderNotifier.format_tender_alert(tender)
                        st.code(alert_text, language="markdown")
                        st.toast("Dispatched webhook payload!", icon="📨")

                # Bid Submission Pack Generator Section
                with st.expander("🗂️ Generate Bid Submission Pack (Cover Letter, Annexures, Checklists)", expanded=False):
                    profile_data = {}
                    try:
                        with open(COMPANY_PROFILE_PATH, "r", encoding="utf-8") as pf:
                            profile_data = json.load(pf)
                    except Exception:
                        pass

                    safe_id = "".join(c for c in tender.id if c.isalnum() or c in ("-", "_"))[:25]
                    pack_col1, pack_col2 = st.columns([2.5, 1.5])
                    with pack_col1:
                        st.caption("Auto-generated submission pack aligned with Indian Public Procurement & SPMCIL guidelines.")
                    with pack_col2:
                        zip_data = BidPackGenerator.create_bid_pack_zip(tender, profile_data)
                        st.download_button(
                            label="📦 Download Complete Pack (.ZIP)",
                            data=zip_data,
                            file_name=f"Bid_Pack_{safe_id}.zip",
                            mime="application/zip",
                            key=f"zip_dl_{tender.id}",
                            use_container_width=True
                        )

                    tab_cov, tab_prof, tab_blk, tab_chk = st.tabs([
                        "📄 Cover Letter",
                        "📋 Bidder Profile Annexure",
                        "⚖️ Non-Blacklisting Undertaking",
                        "✅ Compliance Checklist"
                    ])
                    with tab_cov:
                        cov_txt = BidPackGenerator.generate_cover_letter(tender, profile_data)
                        st.markdown(cov_txt)
                        st.download_button("💾 Download Cover Letter (.md)", cov_txt, file_name=f"Cover_Letter_{safe_id}.md", key=f"cov_dl_{tender.id}")
                    with tab_prof:
                        prof_txt = BidPackGenerator.generate_bidder_profile(tender, profile_data)
                        st.markdown(prof_txt)
                        st.download_button("💾 Download Bidder Profile (.md)", prof_txt, file_name=f"Bidder_Profile_{safe_id}.md", key=f"prof_dl_{tender.id}")
                    with tab_blk:
                        blk_txt = BidPackGenerator.generate_non_blacklisting_undertaking(tender, profile_data)
                        st.markdown(blk_txt)
                        st.download_button("💾 Download Undertaking (.md)", blk_txt, file_name=f"Undertaking_{safe_id}.md", key=f"blk_dl_{tender.id}")
                    with tab_chk:
                        chk_txt = BidPackGenerator.generate_checklist(tender, profile_data)
                        st.markdown(chk_txt)
                        st.download_button("💾 Download Checklist (.md)", chk_txt, file_name=f"Checklist_{safe_id}.md", key=f"chk_dl_{tender.id}")

elif selected_view == "📄 Upload & Analyze Custom PDF":
    st.subheader("📄 Upload Any Tender Document (NIT / RFP / BOQ)")
    st.write("Upload a PDF document to run instant automated extraction, eligibility evaluation, and compliance checklist generation.")

    uploaded_file = st.file_uploader("Choose a Tender PDF file", type=["pdf"])

    if uploaded_file is not None:
        temp_path = TENDERS_DIR / uploaded_file.name
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"Uploaded `{uploaded_file.name}` ({uploaded_file.size / 1024:.1f} KB)")

        with st.spinner("Extracting text and running intelligent eligibility evaluation..."):
            extracted_text = DocumentParser.extract_text_from_pdf(str(temp_path))
            
            # Detect organization and submission deadline from document text
            detected_org = "Procuring Authority"
            text_head = extracted_text[:12000]
            if re.search(r"BA\s*NK\s*NOTE\s*PAPER\s*MILL|BNPM", text_head, re.IGNORECASE):
                detected_org = "Bank Note Paper Mill India Private Limited (BNPM)"
            elif "INDIA SECURITY PRESS" in text_head.upper():
                detected_org = "India Security Press (ISP Nashik) / SPMCIL"
            elif "SPMCIL" in text_head.upper() or "SECURITY PRINTING" in text_head.upper():
                detected_org = "Security Printing and Minting Corporation of India Limited (SPMCIL)"

            m_due = re.search(r"(?:closing\s+date|submission\s+deadline|last\s+date|due\s+date).*?(\d{2}[\.\/\-]\d{2}[\.\/\-]\d{4})", text_head, re.IGNORECASE)
            detected_due = m_due.group(1).replace(".", "-").replace("/", "-") if m_due else "Refer to NIT schedule"

            report = analyzer.analyze_tender(
                tender_title=uploaded_file.name.replace(".pdf", ""),
                tender_text=extracted_text,
                metadata={"organization": detected_org, "due_date": detected_due}
            )

        st.markdown("### 📊 Automated Evaluation Results")
        
        score = report.overall_match_score
        c1, c2, c3 = st.columns(3)
        c1.metric("Overall Match Score", f"{score}/100")
        c2.metric("Verdict", report.qualification_status)
        c3.metric("Required Compliance Exhibits", len(report.required_documents))

        st.progress(score / 100.0)

        st.markdown("#### 📝 Executive Summary")
        st.write(report.summary)

        col_a, col_b = st.columns([1.5, 1])
        with col_a:
            st.markdown("#### ⚖️ Parameter Eligibility Matrix")
            for item in report.eligibility_breakdown:
                icon = "✅" if item.is_eligible else "❌"
                st.markdown(f"**{icon} {item.parameter}**")
                st.caption(f"Required: `{item.required_value}` | Company: `{item.company_value}` — *{item.remarks}*")

        with col_b:
            st.markdown("#### 📋 Required Submissions")
            for doc in report.required_documents:
                st.write(f"• {doc}")
            
            if report.penalties_and_risks:
                st.markdown("#### ⚠️ Identified Risks & Clauses")
                for r in report.penalties_and_risks:
                    st.caption(f"⚠️ {r}")

        st.markdown("---")
        # Check if an existing monitored tender matches this uploaded document
        all_tenders = db.get_all_tenders()
        matched_tender = None
        for t in all_tenders:
            if (t.doc_url and uploaded_file.name in t.doc_url) or (t.doc_path and uploaded_file.name in t.doc_path):
                matched_tender = t
                break
            if "19796" in uploaded_file.name and "19796" in t.id:
                matched_tender = t
                break

        if matched_tender:
            st.success(f"🔗 **Linked to Monitored Portal Tender:** `{matched_tender.id}`")
            st.write(f"**Authority:** {matched_tender.organization} | **Submission Due:** `{matched_tender.due_date}`")
            u_col1, u_col2 = st.columns([2, 2])
            with u_col1:
                if st.button("💾 Sync & Save Evaluation to Radar", key="sync_radar_btn"):
                    matched_tender.doc_path = str(temp_path)
                    matched_tender.analysis_report = report
                    matched_tender.match_score = score
                    matched_tender.status = BidDecisionStatus.HIGH_MATCH if score >= 75 else BidDecisionStatus.REVIEW_NEEDED
                    db.save_tender(matched_tender)
                    st.success("Tender successfully updated and synced with Active Radar!")
                    st.rerun()
            with u_col2:
                st.info("💡 You can view this bid under **📡 Live Tender Radar** (switch sort to 'Match Score' or search 'Nashik').")
        else:
            if st.button("💾 Save to Active Monitored Radar", key="save_new_radar_btn"):
                new_record = TenderRecord(
                    id=f"UPLOAD/{datetime.now().strftime('%Y%m%d%H%M')}",
                    title=uploaded_file.name.replace(".pdf", ""),
                    organization="Uploaded Document Authority",
                    portal=TenderSource.MANUAL_UPLOAD,
                    due_date=report.submission_deadline or datetime.now().strftime("%Y-%m-%d"),
                    doc_path=str(temp_path),
                    match_score=score,
                    status=BidDecisionStatus.HIGH_MATCH if score >= 75 else BidDecisionStatus.REVIEW_NEEDED,
                    analysis_report=report
                )
                db.save_tender(new_record)
                st.success("Tender saved to radar!")
                st.rerun()

elif selected_view == "💼 Bid Pipeline & Corrigendums":
    st.subheader("💼 Active Bidding Pipeline")
    pursuing_tenders = [t for t in db.get_all_tenders() if t.status == BidDecisionStatus.PURSUING]

    if not pursuing_tenders:
        st.info("No tenders currently marked as 'Pursuing Bid'. Go to the **Live Tender Radar** tab and click '🚀 Pursue Bid' on qualified opportunities.")
    else:
        for pt in pursuing_tenders:
            val_cr = (pt.estimated_value_inr / 10000000.0) if pt.estimated_value_inr else 0.0
            st.markdown(f"### 🎯 {pt.title}")
            st.write(f"**Authority:** {pt.organization} | **Est. Value:** ₹{val_cr:.2f} Cr | **Submission Due:** `{pt.due_date}`")
            
            p_c1, p_c2, p_c3 = st.columns([1.5, 1.3, 1.2])
            with p_c1:
                num_docs = len(pt.analysis_report.required_documents) if (pt.analysis_report and pt.analysis_report.required_documents) else 6
                st.write(f"**Checklist Readiness:** {num_docs} Mandatory exhibits identified.")
            with p_c2:
                profile_data = {}
                try:
                    with open(COMPANY_PROFILE_PATH, "r", encoding="utf-8") as pf:
                        profile_data = json.load(pf)
                except Exception:
                    pass
                safe_id = "".join(c for c in pt.id if c.isalnum() or c in ("-", "_"))[:20]
                zip_data = BidPackGenerator.create_bid_pack_zip(pt, profile_data)
                st.download_button(
                    label="📦 Download Bid Pack (.ZIP)",
                    data=zip_data,
                    file_name=f"Bid_Pack_{safe_id}.zip",
                    mime="application/zip",
                    key=f"pipe_zip_{pt.id}",
                    use_container_width=True
                )
            with p_c3:
                if st.button(f"Mark as Submitted ✅", key=f"sub_{pt.id}"):
                    db.update_status(pt.id, BidDecisionStatus.SUBMITTED)
                    st.rerun()
            st.markdown("---")

    st.subheader("📢 Corrigendum Watchdog Feed & Live Impact Diff")
    st.write("Tracks all addendums, date extensions, and specification amendments with automated differential analysis.")

    all_tenders_list = db.get_all_tenders()
    corrigendum_items = []
    for t in all_tenders_list:
        for c in t.corrigendums:
            c_dict = c if isinstance(c, dict) else c.model_dump()
            corrigendum_items.append((t, c_dict))

    if corrigendum_items:
        for t, c_dict in corrigendum_items:
            corr_id = c_dict.get('corrigendum_id', 'CORR')
            pub_date = c_dict.get('published_date', 'N/A')
            impact = c_dict.get('qualification_impact', 'Terms amended')
            diff_list = c_dict.get('diff_items', [])

            with st.expander(f"⚠️ **[{corr_id}]** {t.title} — *{t.organization}* | Published: `{pub_date}`", expanded=True):
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    st.write(f"**Tender Ref ID:** `{t.id}` | **Issuing Authority:** {t.organization}")
                    st.write(f"**Current Radar Due Date:** `{t.due_date}`")
                with c_head2:
                    st.info(f"⚡ **Impact:** {impact}")

                if diff_list:
                    st.markdown("#### 🔍 Structured Differential Analysis (Side-by-Side):")
                    diff_rows = []
                    for di in diff_list:
                        d_dict = di if isinstance(di, dict) else di.model_dump()
                        diff_rows.append({
                            "Parameter": d_dict.get("parameter"),
                            "🔴 Original NIT (v1.0)": d_dict.get("original_value"),
                            "🟢 Amended Terms (v1.1)": d_dict.get("amended_value"),
                            "⚡ Delta / Impact": d_dict.get("delta_summary"),
                            "Severity": d_dict.get("severity"),
                            "Action Required": d_dict.get("action_required")
                        })
                    st.dataframe(pd.DataFrame(diff_rows), use_container_width=True, hide_index=True)
                else:
                    st.markdown(f"**Description:** {c_dict.get('description')}")

                if c_dict.get("document_url"):
                    st.markdown(f"🔗 [Download Official Corrigendum Document PDF]({c_dict.get('document_url')})")
    else:
        st.info("No active corrigendums recorded in system.")

    st.markdown("---")

    # 2. Interactive Corrigendum Auto-Diff Tool
    st.subheader("🔍 Run Corrigendum Auto-Diff on Any Tender")
    st.write("Compare any newly published amendment notice against an active tender to automatically extract dates, financial deltas, and recalculate match scores.")

    target_tender_options = {f"[{t.id[:30]}] {t.title[:60]}... ({t.organization})": t for t in all_tenders_list}
    if not target_tender_options:
        st.info("No monitored tenders available in database.")
    else:
        selected_tender_label = st.selectbox("Select Target Monitored Tender:", list(target_tender_options.keys()))
        selected_tender = target_tender_options[selected_tender_label]

        tab_paste, tab_pdf = st.tabs(["📝 Paste Corrigendum Notice Text", "📄 Upload Corrigendum PDF"])

        corr_input_text = ""
        with tab_paste:
            corr_input_text = st.text_area(
                "Paste Corrigendum Text / Notice Clauses:",
                height=150,
                placeholder="Example:\nCORRIGENDUM NO. 01\n1. The closing date for submission of bids is hereby extended to 30.11.2026.\n2. EMD waiver for MSME / Udyam registered bidders is approved.\n3. PBG reduced to 3% of contract value.\n4. Read 'Dry Offset Platemaking Machine with 2400 DPI' instead of 'Platemaking Machine with 1200 DPI'."
            )

        with tab_pdf:
            uploaded_corr_pdf = st.file_uploader("Upload Corrigendum PDF Document:", type=["pdf"], key="corr_pdf_uploader")
            if uploaded_corr_pdf:
                c_temp_path = TENDERS_DIR / uploaded_corr_pdf.name
                with open(c_temp_path, "wb") as f:
                    f.write(uploaded_corr_pdf.getbuffer())
                corr_input_text = DocumentParser.extract_text_from_pdf(str(c_temp_path))
                st.success(f"Extracted {len(corr_input_text)} characters from `{uploaded_corr_pdf.name}`")

        c_col1, c_col2 = st.columns([1.5, 2.5])
        with c_col1:
            corr_ref_no = st.text_input("Corrigendum Reference / Number", value="CORR-01")
        with c_col2:
            corr_pub_date = st.date_input("Corrigendum Publication Date", value=datetime.now()).strftime("%Y-%m-%d")

        if st.button("🚀 Analyze & Generate Auto-Diff Impact Matrix", key="btn_run_diff"):
            if not corr_input_text.strip():
                st.warning("Please paste corrigendum text or upload a corrigendum PDF.")
            else:
                with st.spinner("Analyzing text and running differential extraction..."):
                    corr_result = diff_engine.compare(
                        tender=selected_tender,
                        corrigendum_text=corr_input_text,
                        corrigendum_id=corr_ref_no,
                        published_date=corr_pub_date
                    )
                    st.session_state["latest_diff_result"] = (selected_tender, corr_result)

        if "latest_diff_result" in st.session_state:
            target_t, c_res = st.session_state["latest_diff_result"]
            st.markdown("### 📊 Auto-Diff Comparison & Impact Matrix")

            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric("Detected Amended Fields", f"{len(c_res.amended_fields)}")
            with m_col2:
                old_s = c_res.old_score or target_t.match_score
                new_s = c_res.new_score or target_t.match_score
                delta_s = new_s - old_s
                st.metric("Score Impact", f"{new_s}%", delta=f"{delta_s:+d}%" if delta_s != 0 else "Unchanged")
            with m_col3:
                st.metric("Qualification Impact", "Qualified" if new_s >= 75 else "Review Needed")

            st.info(f"⚡ **Evaluation Summary:** {c_res.qualification_impact}")

            diff_display_rows = []
            for di in c_res.diff_items:
                d_dict = di if isinstance(di, dict) else di.model_dump()
                diff_display_rows.append({
                    "Parameter": d_dict.get("parameter"),
                    "🔴 Original NIT (v1.0)": d_dict.get("original_value"),
                    "🟢 Amended Terms (v1.1)": d_dict.get("amended_value"),
                    "⚡ Delta / Impact": d_dict.get("delta_summary"),
                    "Severity": d_dict.get("severity"),
                    "Action Required": d_dict.get("action_required")
                })

            st.dataframe(pd.DataFrame(diff_display_rows), use_container_width=True, hide_index=True)

            if st.button("💾 Apply Amendment & Update Live Tender Radar", key="btn_apply_corr"):
                for di in c_res.diff_items:
                    if di.parameter == "Submission Due Date":
                        target_t.due_date = di.amended_value

                if c_res.new_score:
                    target_t.match_score = c_res.new_score
                    target_t.status = BidDecisionStatus.HIGH_MATCH if c_res.new_score >= 75 else BidDecisionStatus.REVIEW_NEEDED

                existing_corrs = [c for c in target_t.corrigendums if (c.corrigendum_id if hasattr(c, 'corrigendum_id') else c.get('corrigendum_id')) != c_res.corrigendum_id]
                existing_corrs.append(c_res)
                target_t.corrigendums = existing_corrs

                db.save_tender(target_t)

                email_cfg = EmailNotifier.load_config()
                if email_cfg.get("enabled") and email_cfg.get("notify_on_corrigendum"):
                    EmailNotifier.send_corrigendum_alert(target_t, c_res)

                st.success(f"Successfully applied amendment [{c_res.corrigendum_id}] to [{target_t.id}]! Tender Radar and Due Dates updated.")
                del st.session_state["latest_diff_result"]
                st.rerun()

elif selected_view == "🔔 Email Alerts & Autonomous Watchdog":
    st.subheader("🔔 Autonomous Watchdog & Instant Email Alert Pipeline")
    st.write("Configure the autonomous background polling daemon and enterprise SMTP email notification pipeline.")

    # 1. Watchdog Daemon Status & Controls
    wd_status = watchdog.get_status()
    is_active = wd_status["is_running"]

    if is_active:
        st.success(f"🟢 **Autonomous Watchdog Daemon is ACTIVE** — Monitoring portals every {wd_status['interval_minutes']} minutes in background.")
    else:
        st.info("⏸️ **Autonomous Watchdog Daemon is IDLE / STOPPED** — Click 'Start Service' below to begin continuous 24/7 background monitoring.")

    w_col1, w_col2, w_col3, w_col4 = st.columns(4)
    with w_col1:
        st.metric("Daemon Status", "Running 🟢" if is_active else "Idle ⏸️")
    with w_col2:
        st.metric("Cycles Executed", f"{wd_status['total_cycles']}")
    with w_col3:
        st.metric("New Bids Discovered", f"{wd_status['new_tenders_found']}")
    with w_col4:
        st.metric("Email Alerts Sent", f"{wd_status['alerts_dispatched']}")

    st.caption(f"**Last Cycle:** {wd_status['last_run_time']} | **Next Scheduled:** {wd_status['next_run_time']} | **Log:** {wd_status['status_message']}")

    btn_w1, btn_w2, btn_w3 = st.columns([1.5, 1.5, 2.0])
    with btn_w1:
        if not is_active:
            if st.button("▶️ Start Watchdog Service", use_container_width=True):
                watchdog.start()
                st.toast("Autonomous Watchdog Service started!", icon="🚀")
                st.rerun()
        else:
            st.button("▶️ Service Already Active", disabled=True, use_container_width=True)

    with btn_w2:
        if is_active:
            if st.button("⏹️ Stop Watchdog Service", use_container_width=True):
                watchdog.stop()
                st.toast("Autonomous Watchdog stopped.", icon="⏹️")
                st.rerun()
        else:
            st.button("⏹️ Service Not Running", disabled=True, use_container_width=True)

    with btn_w3:
        if st.button("⚡ Run Immediate Probe Cycle Now", use_container_width=True):
            with st.spinner("Executing immediate portal probe cycle..."):
                res = watchdog.run_cycle_now()
                if res.get("success"):
                    st.success(f"Cycle completed! Discovered {res.get('new_tenders', 0)} new tenders, sent {res.get('alerts_sent', 0)} alerts.")
                else:
                    st.error(f"Cycle failed: {res.get('error')}")
                st.rerun()

    st.markdown("---")

    # 2. Alert Recipient & Dispatch Preferences (Sender details handled statically in code)
    st.subheader("📬 Alert Recipient & Dispatch Preferences")
    email_cfg = EmailNotifier.load_config()

    with st.form("email_settings_form"):
        e_enabled = st.checkbox("Enable Automated Email Notifications", value=email_cfg.get("enabled", False))

        recipients_str = st.text_area(
            "Recipient Email Addresses (comma-separated)",
            value=", ".join(email_cfg.get("recipient_emails", [])),
            help="Enter one or more email addresses that should receive high-priority alerts."
        )

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            min_score = st.slider("Minimum Match Score for Instant Alert (%)", min_value=50, max_value=95, value=int(email_cfg.get("min_alert_score", 75)), step=5)
        with col_p2:
            interval_min = st.selectbox(
                "Watchdog Polling Interval",
                [30, 60, 120, 180, 360, 720],
                index=[30, 60, 120, 180, 360, 720].index(email_cfg.get("watchdog_interval_minutes", 180)) if email_cfg.get("watchdog_interval_minutes", 180) in [30, 60, 120, 180, 360, 720] else 3,
                format_func=lambda x: f"{x} minutes ({x // 60} hours)" if x >= 60 else f"{x} minutes"
            )

        notify_corri = st.checkbox("Alert on New Corrigendums / Date Extensions", value=email_cfg.get("notify_on_corrigendum", True))

        saved = st.form_submit_button("💾 Save Alert Preferences")
        if saved:
            new_recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
            updated_cfg = {
                "enabled": e_enabled,
                "recipient_emails": new_recipients,
                "min_alert_score": int(min_score),
                "notify_on_corrigendum": notify_corri,
                "watchdog_interval_minutes": int(interval_min)
            }
            if EmailNotifier.save_config(updated_cfg):
                st.success("Alert preferences saved successfully!")
                st.rerun()
            else:
                st.error("Failed to save email configuration.")

    st.markdown("---")

    # 3. Email Test & Diagnostic Suite
    st.subheader("🧪 SMTP Diagnostics & Test Suite")
    st.write("Send test alerts to verify that your email credentials can successfully reach your inbox.")

    d_col1, d_col2 = st.columns(2)
    with d_col1:
        st.markdown("#### 📨 Send Verification Test Email")
        test_email_target = st.text_input("Test Target Email", value=email_cfg.get("recipient_emails", [""])[0] if email_cfg.get("recipient_emails") else "", key="test_email_input")
        if st.button("📤 Send Test Verification Email", use_container_width=True):
            if not test_email_target:
                st.warning("Please enter a target email address.")
            else:
                with st.spinner(f"Dispatching test message to {test_email_target}..."):
                    ok, msg = EmailNotifier.send_test_email(test_email_target.strip())
                    if ok:
                        st.success(f"✅ Test email successfully sent! Check your inbox ({test_email_target}).")
                    else:
                        st.error(f"❌ Failed to send test email: {msg}")

    with d_col2:
        st.markdown("#### 🎯 Send Sample Tender Alert Email")
        st.caption("Sends an authentic HTML tender alert for the **ISP Nashik CToP Machine Tender (84% Match)**.")
        if st.button("🚀 Send Live Sample Tender Alert", use_container_width=True):
            if not test_email_target:
                st.warning("Please enter a target email address on the left.")
            else:
                all_t = db.get_all_tenders()
                sample_t = next((t for t in all_t if "19796" in t.id or "CToP" in t.title), all_t[0] if all_t else None)
                if sample_t:
                    with st.spinner("Dispatching formatted HTML tender alert..."):
                        ok, msg = EmailNotifier.send_tender_alert(sample_t, recipients=[test_email_target.strip()])
                        if ok:
                            st.success(f"✅ Sample alert sent! Check your inbox to review the formatted HTML card.")
                        else:
                            st.error(f"❌ Dispatch error: {msg}")
                else:
                    st.warning("No sample tender found in database.")

elif selected_view == "⚙️ Company Profile Config":
    st.subheader("⚙️ Company Qualification Baseline & Profile")
    st.write("Adjust your company's credentials below. Changing these values allows the agent to recalibrate eligibility scores across all monitored tenders.")

    with open(COMPANY_PROFILE_PATH, "r", encoding="utf-8") as f:
        curr_prof = json.load(f)

    with st.form("company_profile_form"):
        co_name = st.text_input("Company Legal Name", curr_prof.get("company_name", ""))
        
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            co_turnover = st.number_input("Average Annual Turnover (₹ Crores)", value=float(curr_prof.get("financials", {}).get("annual_turnover_inr_cr", 25.0)), min_value=0.1, step=1.0)
            co_emd = st.number_input("Max EMD Liquidity / Bank Guarantee (₹ Lakhs)", value=float(curr_prof.get("financials", {}).get("max_emd_capacity_inr_lakhs", 50.0)), min_value=1.0, step=5.0)
        with c_f2:
            co_exp = st.number_input("Years in Business", value=int(curr_prof.get("experience", {}).get("years_in_business", 8)), min_value=1, step=1)
            co_orders = st.number_input("Largest Completed Order (₹ Crores)", value=float(curr_prof.get("experience", {}).get("largest_single_order_inr_cr", 10.0)), min_value=0.1, step=1.0)

        certs_str = st.text_area("Held Certifications (comma separated)", ", ".join(curr_prof.get("certifications", [])))
        keywords_str = st.text_area("Target Domain Keywords (comma separated)", ", ".join(curr_prof.get("keywords", [])))

        submitted = st.form_submit_button("💾 Save Profile & Recalculate All Tender Scores")

        if submitted:
            updated_profile = {
                "company_name": co_name,
                "sectors": curr_prof.get("sectors", []),
                "keywords": [k.strip() for k in keywords_str.split(",") if k.strip()],
                "financials": {
                    "annual_turnover_inr_cr": co_turnover,
                    "net_worth_inr_cr": curr_prof.get("financials", {}).get("net_worth_inr_cr", 8.5),
                    "max_emd_capacity_inr_lakhs": co_emd
                },
                "certifications": [c.strip() for c in certs_str.split(",") if c.strip()],
                "experience": {
                    "years_in_business": co_exp,
                    "completed_govt_projects": curr_prof.get("experience", {}).get("completed_govt_projects", 10),
                    "largest_single_order_inr_cr": co_orders
                },
                "preferred_locations": curr_prof.get("preferred_locations", [])
            }

            with open(COMPANY_PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(updated_profile, f, indent=2)

            re_analyzer = TenderAnalyzer(company_profile_path=COMPANY_PROFILE_PATH)
            for t in db.get_all_tenders():
                rep = re_analyzer.analyze_tender(
                    tender_title=t.title,
                    tender_text=f"{t.title} {t.category} {t.organization}",
                    metadata={"organization": t.organization, "estimated_value_inr": t.estimated_value_inr, "emd_amount_inr": t.emd_amount_inr, "due_date": t.due_date}
                )
                t.match_score = rep.overall_match_score
                t.analysis_report = rep
                db.save_tender(t)

            st.success("Company profile saved and all tender match scores recalculated successfully!")
            st.rerun()

# ----------------- SCREEN 5: LIVE SCRAPING LOGS & AUDIT TRAIL -----------------
elif selected_view == "📋 Live Scraping Logs & Audit Trail":
    st.subheader("📋 Production Scraping Logs & Portal Audit Trail")
    st.write(
        "Real-time visibility into all network requests, portal probes, HTTP status codes, "
        "response latencies, and security challenges encountered across monitored Indian portals."
    )

    log_actions_col1, log_actions_col2, log_actions_col3 = st.columns([1.5, 2, 1.5])
    with log_actions_col1:
        if st.button("🔄 Refresh Live Logs", key="refresh_logs_btn"):
            st.rerun()
    with log_actions_col2:
        if st.button("🌐 Execute Full Portal Probe & Scrape Cycle", key="run_probe_cycle_btn"):
            with st.spinner("Probing live GeM & CPPP endpoints and logging responses..."):
                scraper_inst = IndianTenderScraper(analyzer=analyzer)
                new_tenders = scraper_inst.fetch_curated_indian_tenders()
                for item in new_tenders:
                    db.save_tender(item)
            st.success("Portal scrape cycle executed and logged!")
            st.rerun()

    # Dynamic Portal Registration & URL Management
    with st.expander("🌐 **Manage & Add More Portal URLs to Monitor**", expanded=False):
        st.write("Register additional central, state, PSU, or international procurement URLs for autonomous monitoring and network probing.")
        
        reg_portals = IndianTenderScraper.get_registered_portals()
        if reg_portals:
            st.markdown("##### 📌 Currently Registered Target Portals:")
            p_cols = st.columns(3)
            for idx, p in enumerate(reg_portals):
                col_idx = idx % 3
                with p_cols[col_idx]:
                    st.caption(f"**{p.get('name')}** ({p.get('category')})\n\n🔗 `{p.get('url')}`")

        st.markdown("---")
        st.markdown("##### ➕ Register a New Portal URL:")
        with st.form("add_portal_form"):
            ap_c1, ap_c2 = st.columns(2)
            with ap_c1:
                new_portal_name = st.text_input("Portal Name", placeholder="e.g. Karnataka KPPP or IOCL Tenders")
                new_portal_cat = st.selectbox("Category", ["Central Government", "State Government", "Railways & Transport", "Defence & Security", "Public Sector / PSU", "International / Global"])
            with ap_c2:
                new_portal_url = st.text_input("Portal Home URL", placeholder="https://kppp.karnataka.gov.in")
                new_bids_url = st.text_input("Bids Listing URL (Optional)", placeholder="https://kppp.karnataka.gov.in/portal-bids")

            add_btn = st.form_submit_button("🚀 Add Portal & Test Probe Now")

            if add_btn:
                if not new_portal_name or not new_portal_url:
                    st.error("Please provide both Portal Name and Target URL.")
                else:
                    if not new_portal_url.startswith("http"):
                        new_portal_url = "https://" + new_portal_url
                    
                    IndianTenderScraper.register_portal(
                        name=new_portal_name,
                        url=new_portal_url,
                        category=new_portal_cat,
                        bids_url=new_bids_url if new_bids_url else new_portal_url
                    )
                    
                    test_scraper = IndianTenderScraper(analyzer=analyzer)
                    probe_res = test_scraper.probe_portal(new_portal_name, new_portal_url)
                    
                    if probe_res.get("success"):
                        st.success(f"Registered and successfully probed '{new_portal_name}'! (Latency: {probe_res.get('latency_ms', 0):.1f}ms)")
                    else:
                        st.warning(f"Registered '{new_portal_name}'. Probe response code: {probe_res.get('status_code')}")
                    st.rerun()

    audit_events = ScrapingAuditLogger.get_recent_audit_events(limit=50)

    # Metrics Summary
    if audit_events:
        total_probes = len(audit_events)
        status_200s = sum(1 for e in audit_events if e.get("http_status") == 200)
        latencies = [e["response_time_ms"] for e in audit_events if e.get("response_time_ms") is not None]
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0
        unique_urls = len(set(e.get("target_url", "") for e in audit_events if e.get("target_url")))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Logged Network Events", f"{total_probes}")
        m2.metric("Successful (200 OK)", f"{status_200s}", delta=f"{(status_200s/total_probes)*100:.0f}% success")
        m3.metric("Avg Response Time", f"{avg_lat:.1f} ms")
        m4.metric("Monitored Endpoints", f"{unique_urls}")

        st.markdown("---")
        st.markdown("#### 🌐 Target URLs & Scraping Activity Audit")
        
        # Format table data
        table_rows = []
        for ev in audit_events:
            table_rows.append({
                "Timestamp": ev.get("timestamp", "").replace("T", " ")[:19],
                "Portal": ev.get("target_portal", "N/A"),
                "Action": ev.get("action", ""),
                "HTTP Status": str(ev.get("http_status") or "N/A"),
                "Latency (ms)": f"{ev.get('response_time_ms', 0):.1f}" if ev.get("response_time_ms") is not None else "-",
                "Payload (Bytes)": ev.get("payload_bytes", "-"),
                "Target URL": ev.get("target_url", ""),
                "Details": ev.get("details", "") or ev.get("error", "")
            })

        df_logs = pd.DataFrame(table_rows)
        st.dataframe(df_logs, width="stretch", hide_index=True)
    else:
        st.info("No audit logs recorded yet. Click 'Execute Full Portal Probe & Scrape Cycle' to trigger real portal network queries.")

    st.markdown("---")
    st.markdown("#### 📜 Live Rotating File Log Stream (`tender_agent.log`)")
    
    col_filter, col_download = st.columns([2, 1])
    with col_filter:
        log_level_filter = st.selectbox("Filter Log Level", ["ALL", "INFO", "WARNING", "ERROR"])

    raw_logs = ScrapingAuditLogger.get_recent_raw_logs(limit_lines=150)
    
    if raw_logs:
        if log_level_filter != "ALL":
            filtered_logs = [line for line in raw_logs if f"[{log_level_filter}" in line]
        else:
            filtered_logs = raw_logs

        st.code("\n".join(filtered_logs), language="log")
    else:
        st.caption("Log file is currently empty.")

    with col_download:
        if LOG_FILE_PATH.exists():
            with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as lf:
                st.download_button(
                    label="📥 Download Full System Log",
                    data=lf.read(),
                    file_name="tender_agent.log",
                    mime="text/plain"
                )

