import streamlit as st
import os
import json
from datetime import datetime
import pandas as pd
from config.settings import COMPANY_PROFILE_PATH, TENDERS_DIR, LOG_FILE_PATH, AUDIT_LOG_PATH
from core.database import TenderDatabase
from core.scraper import IndianTenderScraper
from core.analyzer import TenderAnalyzer
from core.document_parser import DocumentParser
from core.notifier import TenderNotifier
from core.models import TenderRecord, BidDecisionStatus, TenderSource
from core.logger import get_agent_logger, ScrapingAuditLogger

logger = get_agent_logger("Dashboard")

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

with st.sidebar:
    st.title("🛡️ TenderPulse Agent")
    st.caption("AI-Powered Procurement Intelligence for GeM & CPPP")
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
    st.markdown("✅ **State eProcurement Hubs**")

    st.markdown("---")
    if st.button("🔄 Refresh & Sync Live Feeds", use_container_width=True):
        scraper = IndianTenderScraper(analyzer=analyzer)
        new_items = scraper.fetch_curated_indian_tenders()
        for item in new_items:
            db.save_tender(item)
        st.toast("Synchronized live tenders from GeM & CPPP!", icon="✅")
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

tab_radar, tab_upload, tab_pipeline, tab_profile, tab_logs = st.tabs([
    "📡 Live Tender Radar",
    "📄 Upload & Analyze Custom PDF",
    "💼 Bid Pipeline & Corrigendums",
    "⚙️ Company Profile Config",
    "📋 Live Scraping Logs & Audit Trail"
])

with tab_radar:
    f_col1, f_col2, f_col3 = st.columns([1.5, 1.5, 2])
    with f_col1:
        portal_filter = st.selectbox("Portal Filter", ["All Portals", "GeM (Gov e-Marketplace)", "CPPP (eProcure)"])
    with f_col2:
        status_filter = st.selectbox("Match Status", ["All Statuses", "High Match (Qualified)", "Review Needed", "Disqualified", "Pursuing Bid"])
    with f_col3:
        search_query = st.text_input("🔍 Search keyword, department or tender ID", "")

    all_tenders = db.get_all_tenders()

    filtered_tenders = []
    for t in all_tenders:
        portal_str = t.portal.value if hasattr(t.portal, 'value') else t.portal
        status_str = t.status.value if hasattr(t.status, 'value') else t.status

        if portal_filter != "All Portals" and portal_str != portal_filter:
            continue
        if status_filter != "All Statuses" and status_str != status_filter:
            continue
        if search_query:
            q = search_query.lower()
            if q not in t.title.lower() and q not in t.organization.lower() and q not in t.id.lower():
                continue
        filtered_tenders.append(t)

    st.write(f"Showing **{len(filtered_tenders)}** tenders matching criteria:")

    if not filtered_tenders:
        st.info("No tenders match the specified filter.")
    else:
        for tender in filtered_tenders:
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

with tab_upload:
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
            
            report = analyzer.analyze_tender(
                tender_title=uploaded_file.name.replace(".pdf", ""),
                tender_text=extracted_text,
                metadata={"organization": "Uploaded Tender Authority", "due_date": "Extracted from document"}
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
        if st.button("💾 Save to Active Monitored Radar"):
            new_record = TenderRecord(
                id=f"UPLOAD/{datetime.now().strftime('%Y%m%d%H%M')}",
                title=uploaded_file.name.replace(".pdf", ""),
                organization="Uploaded Document",
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

with tab_pipeline:
    st.subheader("💼 Active Bidding Pipeline")
    pursuing_tenders = [t for t in db.get_all_tenders() if t.status == BidDecisionStatus.PURSUING]

    if not pursuing_tenders:
        st.info("No tenders currently marked as 'Pursuing Bid'. Go to the **Live Tender Radar** tab and click '🚀 Pursue Bid' on qualified opportunities.")
    else:
        for pt in pursuing_tenders:
            val_cr = (pt.estimated_value_inr / 10000000.0) if pt.estimated_value_inr else 0.0
            st.markdown(f"### 🎯 {pt.title}")
            st.write(f"**Authority:** {pt.organization} | **Est. Value:** ₹{val_cr:.2f} Cr | **Submission Due:** `{pt.due_date}`")
            
            p_c1, p_c2 = st.columns([2, 1])
            with p_c1:
                st.write(f"**Checklist Readiness:** 6 Mandatory exhibits identified.")
            with p_c2:
                if st.button(f"Mark as Submitted ✅", key=f"sub_{pt.id}"):
                    db.update_status(pt.id, BidDecisionStatus.SUBMITTED)
                    st.rerun()
            st.markdown("---")

    st.subheader("📢 Corrigendum Watchdog Feed")
    corrigendum_items = []
    for t in db.get_all_tenders():
        for c in t.corrigendums:
            c_dict = c if isinstance(c, dict) else c.model_dump()
            corrigendum_items.append((t, c_dict))

    if corrigendum_items:
        for t, c in corrigendum_items:
            st.warning(f"**{t.title}** ({t.id})\n\n"
                       f"📅 Published: `{c.get('published_date')}` | Ref: `{c.get('corrigendum_id')}`\n\n"
                       f"👉 {c.get('description')}")
    else:
        st.write("No active corrigendums recorded.")

with tab_profile:
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

# ----------------- TAB 5: LIVE SCRAPING LOGS & AUDIT TRAIL -----------------
with tab_logs:
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
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
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

