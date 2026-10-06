from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class TenderSource(str, Enum):
    GEM = "GeM (Gov e-Marketplace)"
    CPPP = "CPPP (eProcure)"
    STATE_PORTAL = "State eProcurement"
    MANUAL_UPLOAD = "Direct Document Upload"

class BidDecisionStatus(str, Enum):
    DISCOVERED = "Discovered"
    HIGH_MATCH = "High Match (Qualified)"
    REVIEW_NEEDED = "Review Needed"
    DISQUALIFIED = "Disqualified"
    PURSUING = "Pursuing Bid"
    DROPPED = "Dropped"
    SUBMITTED = "Submitted"

class EligibilityItem(BaseModel):
    parameter: str = Field(..., description="e.g. Annual Turnover, Past Experience, ISO Certificate")
    required_value: str = Field(..., description="Value specified in tender document")
    company_value: str = Field(..., description="Matching company capability from profile")
    is_eligible: bool = Field(..., description="Whether company satisfies this criteria")
    risk_level: str = Field(default="Low", description="Low, Medium, High")
    remarks: str = Field(default="", description="Detailed observation or caution")

class TenderAnalysisReport(BaseModel):
    summary: str = Field(..., description="1-page concise executive summary")
    overall_match_score: int = Field(..., ge=0, le=100, description="Score from 0 to 100")
    qualification_status: str = Field(..., description="Qualified, Disqualified, or Conditional")
    estimated_tender_value_inr: Optional[float] = None
    emd_amount_inr: Optional[float] = None
    submission_deadline: Optional[str] = None
    delivery_period: Optional[str] = None
    penalties_and_risks: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    eligibility_breakdown: List[EligibilityItem] = Field(default_factory=list)

class Corrigendum(BaseModel):
    corrigendum_id: str
    tender_id: str
    published_date: str
    description: str
    amended_fields: List[str] = Field(default_factory=list)
    document_url: Optional[str] = None

class TenderRecord(BaseModel):
    id: str = Field(..., description="Unique Tender/Bid Number")
    title: str = Field(..., description="Tender Title / Scope of Work")
    organization: str = Field(..., description="Department, Ministry or PSU")
    portal: TenderSource = TenderSource.GEM
    published_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    due_date: str
    estimated_value_inr: Optional[float] = None
    emd_amount_inr: Optional[float] = None
    category: str = "IT & Electronics"
    location: str = "All India"
    doc_path: Optional[str] = None
    doc_url: Optional[str] = None
    match_score: int = 0
    status: BidDecisionStatus = BidDecisionStatus.DISCOVERED
    analysis_report: Optional[TenderAnalysisReport] = None
    corrigendums: List[Corrigendum] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
