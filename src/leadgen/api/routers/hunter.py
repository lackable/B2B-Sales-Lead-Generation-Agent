"""Hunter.io endpoints: /hunter/*"""

import asyncio
from typing import Dict, List

from fastapi import APIRouter, HTTPException

from leadgen.api.parsers import extract_domain_from_url, hunter_email_count
from leadgen.api.schemas import (
    HunterEmailRequest,
    HunterSmartEnrichDM,
    HunterSmartEnrichRequest,
    StoreEmailRequest,
)
from leadgen.api.state import _email_store
from leadgen.core.clients.hunter import find_email_by_linkedin

router = APIRouter(tags=["hunter"])


@router.post("/hunter/find-email")
async def hunter_find_email(req: HunterEmailRequest):
    """Retrieve email address via Hunter.io API for a specific Decision Maker's LinkedIn profile/handle."""
    if not req.linkedin_url or not req.linkedin_url.strip():
        raise HTTPException(400, "LinkedIn URL or handle is required")

    try:
        res = await asyncio.to_thread(
            find_email_by_linkedin,
            linkedin_input=req.linkedin_url.strip(),
            first_name=req.first_name,
            last_name=req.last_name,
            full_name=req.full_name,
            domain=req.domain,
            company=req.company,
        )
        return res
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))
    except Exception as exc:
        raise HTTPException(500, f"Hunter API error: {exc}")


@router.get("/hunter/email-count")
async def hunter_email_count_endpoint(domain: str):
    """
    Check how many emails Hunter.io has indexed for a given domain.
    FREE endpoint — does not consume Hunter credits.
    Returns { domain, count }.
    """
    count = await asyncio.to_thread(hunter_email_count, domain)
    return {"domain": domain, "count": count}


@router.post("/hunter/smart-enrich")
async def hunter_smart_enrich(req: HunterSmartEnrichRequest):
    """
    Smart sequential email enrichment:
    1. Groups DMs by company domain.
    2. Calls Email Count per domain — skips companies where count == 0.
    3. For each eligible company, sequentially calls Email Finder on DMs (with LinkedIn URLs).
    4. Stops per company once 3 emails have been found.
    5. Returns enriched DMs pinned first, metadata about skipped/stopped companies.
    """
    EMAIL_CAP = 3  # hardcoded per-company cap

    # ── Group DMs by domain ─────────────────────────────────────────────────────
    # domain → list of DMs (preserving original order)
    domain_groups: Dict[str, List[HunterSmartEnrichDM]] = {}

    for dm in req.decision_makers:
        domain = extract_domain_from_url(dm.company_website or "")
        if domain not in domain_groups:
            domain_groups[domain] = []
        domain_groups[domain].append(dm)

    enriched: List[Dict] = []          # DMs with found emails
    skipped_companies: List[str] = []  # count == 0
    stopped_at_cap: List[str] = []     # hit the 3-email cap
    no_indexed: set = set()            # dm IDs whose company had count=0

    # ── Process each domain group ───────────────────────────────────────────────
    for domain, dms in domain_groups.items():
        company_label = dms[0].company_name or domain or "Unknown"

        # Step 1: Email Count gate
        count = await asyncio.to_thread(hunter_email_count, domain)
        if count == 0:
            print(f"[SMART-ENRICH] ⛔ {company_label} — email count=0, skipping", flush=True)
            skipped_companies.append(company_label)
            for dm in dms:
                no_indexed.add(dm.id)
            continue

        print(f"[SMART-ENRICH] ✅ {company_label} — email count={count}, proceeding", flush=True)

        # Step 2: Sequential Email Finder, stop at EMAIL_CAP
        found = 0
        for dm in dms:
            if found >= EMAIL_CAP:
                break
            if not dm.linkedin_url or not dm.linkedin_url.strip():
                continue  # skip DMs without LinkedIn URL silently

            try:
                result = await asyncio.to_thread(
                    find_email_by_linkedin,
                    linkedin_input=dm.linkedin_url.strip(),
                    full_name=dm.name,
                    domain=domain,
                    company=dm.company_name,
                )
                email = result.get("data", {}).get("email") if isinstance(result.get("data"), dict) else None
                score = result.get("data", {}).get("score") if isinstance(result.get("data"), dict) else None

                if email:
                    print(f"[SMART-ENRICH]   📧 Found email for {dm.name}: {email}", flush=True)
                    enriched.append({
                        "id": dm.id,
                        "email": email,
                        "score": score,
                        "raw": result,
                    })
                    found += 1
                else:
                    print(f"[SMART-ENRICH]   — No email for {dm.name}", flush=True)

            except Exception as exc:
                print(f"[SMART-ENRICH]   ⚠️ Error for {dm.name}: {exc}", flush=True)

        if found >= EMAIL_CAP:
            stopped_at_cap.append(company_label)

    enriched_ids = {e["id"] for e in enriched}

    return {
        "enriched": enriched,
        "no_indexed_dm_ids": list(no_indexed),
        "skipped_companies": skipped_companies,
        "stopped_at_cap_companies": stopped_at_cap,
        "total_emails_found": len(enriched_ids),
    }


@router.post("/hunter/store-email")
async def store_email(req: StoreEmailRequest):
    """
    Persist a Hunter-retrieved email to the in-memory store so it is
    available for the consolidated Excel export without re-fetching.
    Called by the frontend immediately after every successful email find.
    """
    if not req.email or not req.email.strip():
        raise HTTPException(400, "email must not be empty")
    key = (req.company_name.strip().lower(), req.dm_name.strip().lower())
    _email_store[key] = req.email.strip()
    return {"stored": True, "key": f"{req.company_name} / {req.dm_name}"}
