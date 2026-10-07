import io
import zipfile
from datetime import datetime
from typing import Dict, Any
from core.models import TenderRecord

class BidPackGenerator:
    """
    Generates standard Indian Public Procurement (GeM / CPPP / SPMCIL / PSU)
    bid submission dossiers, compliance annexures, and cover letters.
    """

    @staticmethod
    def generate_cover_letter(tender: TenderRecord, profile: Dict[str, Any]) -> str:
        co_name = profile.get("company_name", "Bidder Entity Pvt Ltd")
        co_exp = profile.get("experience", {})
        today_str = datetime.now().strftime("%d-%B-%Y")
        
        emd_str = f"₹{tender.emd_amount_inr:,.2f}" if tender.emd_amount_inr else "Exempted as per MSME / Start-up Guidelines"

        return f"""# BID SUBMISSION COVER LETTER
*(To be printed on Official Company Letterhead)*

**Date:** {today_str}

**To:**  
The Tender Inviting Authority  
**{tender.organization}**  

**Subject:** Submission of Bid for *"{tender.title}"*  
**Tender Reference ID:** `{tender.id}`  
**Due Date for Submission:** {tender.due_date}  

Dear Sir / Madam,

Having examined the Tender / RFP Documents including all addendums and corrigendums issued by your esteemed organization, we, **M/s {co_name}**, hereby submit our comprehensive bid proposal for the above-referenced work.

We hereby certify and confirm that:
1. **Unconditional Acceptance:** We have thoroughly read, understood, and accept all clauses, terms, and technical specifications outlined in Tender No. `{tender.id}` without any deviation or reservation.
2. **Eligibility & Capability:** We satisfy all pre-qualification criteria, including financial turnover requirements, past operating experience of {co_exp.get('years_in_business', 5)}+ years, and requisite technical certifications.
3. **Earnest Money Deposit (EMD):** We have remitted / attached the required EMD of **{emd_str}** via the designated mode / provided valid MSME/NSIC exemption certificate.
4. **Bid Validity:** Our offer remains valid for a period of **120 days** from the tender opening date or as stipulated in the NIT.
5. **Two-Envelope Structure:** Our submission has been segregated strictly into Packet-A (Technical & Fee Bid) and Packet-B (Financial / BoQ Bid).

Thank you for the opportunity to participate in this procurement cycle.

Yours faithfully,  
**For and on behalf of M/s {co_name}**

*(Authorized Signatory)*  
Name: ____________________________________  
Designation: Director / Authorized Signatory  
Official Seal / Stamp:  
Contact Email: procurement@{co_name.lower().replace(' ', '')}.com  
Mobile: +91 98XXXXXXXX  
"""

    @staticmethod
    def generate_bidder_profile(tender: TenderRecord, profile: Dict[str, Any]) -> str:
        co_name = profile.get("company_name", "Bidder Entity Pvt Ltd")
        fin = profile.get("financials", {})
        exp = profile.get("experience", {})
        certs = profile.get("certifications", [])

        return f"""# ANNEXURE - I: BIDDER PROFILE & CREDENTIALS
*(Format for Technical Evaluation as per Public Procurement Guidelines)*

| Parameter / Field | Bidder Particulars |
| :--- | :--- |
| **Legal Entity Name** | **{co_name}** |
| **Constitution of Firm** | Private Limited / Public Limited Company |
| **Years in Commercial Operation** | **{exp.get('years_in_business', 5)} Years** |
| **Annual Turnover (Average Last 3 FY)** | **₹{fin.get('annual_turnover_inr_cr', 0.0):.2f} Crore** |
| **Company Net Worth** | **₹{fin.get('net_worth_inr_cr', 0.0):.2f} Crore** |
| **Approved Bank Guarantee / EMD Limit** | **₹{fin.get('max_emd_capacity_inr_lakhs', 0.0):.2f} Lakhs** |
| **Completed Government Projects** | **{exp.get('completed_govt_projects', 0)} Contracts Executed** |
| **Single Largest Order Value** | **₹{exp.get('largest_single_order_inr_cr', 0.0):.2f} Crore** |
| **Accreditations & Certifications** | {', '.join(certs) if certs else 'ISO 9001:2015'} |
| **Goods & Services Tax ID (GSTIN)** | 27AAACXXXXXX1Z9 *(Verified)* |
| **Permanent Account Number (PAN)** | AAACXXXXXX |
| **Registered Office Address** | Mumbai / Nashik / New Delhi, India |

### Key Domain Competencies:
{chr(10).join([f"- {s}" for s in profile.get('sectors', ['Information Technology', 'Industrial Engineering'])])}

I hereby declare that all particulars furnished above are true and verifiable against audited financial statements and client completion certificates.

**Authorized Signatory:** ___________________________  
**Date:** {datetime.now().strftime("%d-%B-%Y")}  
"""

    @staticmethod
    def generate_non_blacklisting_undertaking(tender: TenderRecord, profile: Dict[str, Any]) -> str:
        co_name = profile.get("company_name", "Bidder Entity Pvt Ltd")
        today_str = datetime.now().strftime("%d-%B-%Y")

        return f"""# UNDERTAKING FOR NON-BLACKLISTING & INTEGRITY PACT
*(To be executed on Non-Judicial Stamp Paper of ₹100 or Official Letterhead)*

**Tender Reference:** `{tender.id}`  
**Procuring Entity:** {tender.organization}  
**Date:** {today_str}  

I, _______________________________, in my capacity as Director / Authorized Representative of **M/s {co_name}**, do hereby solemnly affirm and state as under:

1. **No Debarment / Blacklisting:**  
   That **M/s {co_name}**, including our directors, partners, and key managerial personnel, have **NEVER** been debarred, blacklisted, suspended, or put on holiday list by:
   - Any Ministry, Department, or PSU of the Government of India;
   - Security Printing and Minting Corporation of India Limited (SPMCIL) or any of its mints/presses;
   - Government e-Marketplace (GeM) or Central Public Procurement Portal (CPPP);
   - Any State Government or autonomous statutory body.

2. **No Corrupt / Fraudulent Practice:**  
   We uphold the highest ethical standards and strictly abide by the Indian Penal Code, Prevention of Corruption Act (1988), and the Integrity Pact. No employee or agent of ours has offered or will offer any bribe, gift, or inducement to any official associated with this tender.

3. **No Insolvency or Bankruptcy:**  
   The company is not currently under corporate insolvency resolution process (CIRP) under the Insolvency and Bankruptcy Code (IBC, 2016) nor has any winding-up petition been admitted against us.

4. **Authenticity of Submissions:**  
   All certificates, technical data sheets, and financial balance sheets uploaded in support of Tender No. `{tender.id}` are genuine and unmanipulated.

**DEPONENT / AUTHORIZED SIGNATORY**  
For M/s {co_name}  

*(Signature with Company Stamp)*  

**VERIFICATION:**  
Verified at ________________ on this {today_str} that the contents of above affidavit are true to the best of my knowledge and belief.  
"""

    @staticmethod
    def generate_checklist(tender: TenderRecord, profile: Dict[str, Any]) -> str:
        rep = tender.analysis_report
        req_docs = rep.required_documents if rep and rep.required_documents else [
            "GST Registration Certificate",
            "PAN Card Copy",
            "Audited Balance Sheets (Last 3 FY) with CA UDIN",
            "EMD Payment Receipt / Bank Guarantee",
            "OEM Authorization Form (MAF)",
            "Non-Blacklisting Undertaking"
        ]

        exhibits_checklist = "\n".join([f"- [ ] **Item {i+1}:** {doc}" for i, doc in enumerate(req_docs)])

        return f"""# BID SUBMISSION COMPLIANCE CHECKLIST
**Tender:** {tender.title}  
**Authority:** {tender.organization} | **ID:** `{tender.id}`  
**Deadline:** `{tender.due_date}`  

---

### 📦 MANDATORY TENDER EXHIBITS & FORMS
*Ensure all items below are compiled, signed, and submitted in compliance with the tender document instructions:*

{exhibits_checklist}

---

### 💰 PACKET - B: FINANCIAL / BOQ ENVELOPE
*To be uploaded strictly as password-protected / encrypted BoQ file as specified in the portal:*

- [ ] **1. Bill of Quantities (BoQ) Excel Sheet:** Basic unit rate filled without formula tampering.
- [ ] **2. Taxes & Duties Schedule:** GST rate clearly indicated (e.g. 18%).
- [ ] **3. Commercial Terms Compliance:** Confirmation of price validity (120 days) and freight/insurance terms (FOR Destination).

---
*Checklist generated by Autonomous TenderPulse Agent for {profile.get('company_name', 'Bidding Team')}*
"""

    @classmethod
    def create_bid_pack_zip(cls, tender: TenderRecord, profile: Dict[str, Any]) -> bytes:
        """
        Bundles all 4 generated bidding files into a downloadable ZIP archive.
        """
        clean_id = "".join(c for c in tender.id if c.isalnum() or c in ("-", "_"))[:30]
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Cover letter
            cover_letter = cls.generate_cover_letter(tender, profile)
            zip_file.writestr("01_Bid_Submission_Cover_Letter.md", cover_letter)

            # 2. Bidder profile
            bidder_prof = cls.generate_bidder_profile(tender, profile)
            zip_file.writestr("02_Bidder_Information_Annexure.md", bidder_prof)

            # 3. Non-blacklisting
            undertaking = cls.generate_non_blacklisting_undertaking(tender, profile)
            zip_file.writestr("03_Non_Blacklisting_Undertaking.md", undertaking)

            # 4. Checklist
            checklist = cls.generate_checklist(tender, profile)
            zip_file.writestr("04_Compliance_Checklist_Packet_A_and_B.md", checklist)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()
