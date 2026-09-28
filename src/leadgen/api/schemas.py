"""Pydantic request models for the REST API."""

from typing import List, Optional

from pydantic import BaseModel


# ── Shortlister ────────────────────────────────────────────────────────────────

class ShortlisterRequest(BaseModel):
    query: str


# ── LinkedIn Finder ────────────────────────────────────────────────────────────

class LinkedInCompany(BaseModel):
    company_name: str
    linkedin_url: str
    website: str


class LinkedInRequest(BaseModel):
    companies: List[LinkedInCompany]
    concurrency: int = 10


# ── Hunter.io email enrichment ─────────────────────────────────────────────────

class HunterEmailRequest(BaseModel):
    linkedin_url: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    domain: Optional[str] = None
    company: Optional[str] = None


class StoreEmailRequest(BaseModel):
    company_name: str
    dm_name: str
    email: str


class HunterSmartEnrichDM(BaseModel):
    id: str
    name: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    position: Optional[str] = None


class HunterSmartEnrichRequest(BaseModel):
    decision_makers: List[HunterSmartEnrichDM]
