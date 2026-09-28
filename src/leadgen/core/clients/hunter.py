"""
Hunter.io Email Finder API (v2) — retrieve an email via LinkedIn profile/handle.
Documentation: https://hunter.io/api-documentation/v2#email-finder

Library module: the CLI lives in ``scripts/find_email.py``.
"""

import re
from typing import Any, Dict, Optional

import requests

from leadgen import config

HUNTER_EMAIL_FINDER_URL = "https://api.hunter.io/v2/email-finder"


def get_hunter_api_key(provided_key: Optional[str] = None) -> Optional[str]:
    """Retrieve API key from argument or the repo-root .env."""
    return provided_key or config.HUNTER_API_KEY


def extract_linkedin_handle(linkedin_input: str) -> str:
    """
    Extracts the LinkedIn handle from a full LinkedIn URL or returns the handle if already clean.

    Examples:
        'https://www.linkedin.com/in/alexisohanian/' -> 'alexisohanian'
        'http://linkedin.com/in/john-doe-12345'       -> 'john-doe-12345'
        'alexisohanian'                              -> 'alexisohanian'
    """
    linkedin_input = linkedin_input.strip()

    # Pattern to extract handle from linkedin profile URL
    match = re.search(r'linkedin\.com/in/([a-zA-Z0-9%_-]+)', linkedin_input, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('/')

    # Strip any trailing slashes or leading @ if provided directly as handle
    handle = linkedin_input.strip('/').lstrip('@')
    return handle


def find_email_by_linkedin(
    linkedin_input: str,
    api_key: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    full_name: Optional[str] = None,
    domain: Optional[str] = None,
    company: Optional[str] = None,
    max_duration: int = 10
) -> Dict[str, Any]:
    """
    Calls Hunter.io Email Finder API v2 to retrieve an email address.

    :param linkedin_input: Full LinkedIn profile URL or handle (e.g. 'alexisohanian')
    :param api_key: Hunter.io API Key. If None, checks .env file / environment variables.
    :param first_name: Optional person's first name to assist matching
    :param last_name: Optional person's last name to assist matching
    :param full_name: Optional person's full name to assist matching
    :param domain: Optional company domain name (e.g. 'reddit.com')
    :param company: Optional company name (e.g. 'Reddit')
    :param max_duration: Max duration in seconds (3-20). Default: 10
    :return: Dictionary containing the API response data or error details.
    """
    key = get_hunter_api_key(api_key)
    if not key:
        raise ValueError(
            "Hunter API key is required. Specify HUNTER_API_KEY in .env, set environment variable, or pass api_key parameter."
        )

    handle = extract_linkedin_handle(linkedin_input)

    params: Dict[str, Any] = {
        "linkedin_handle": handle,
        "api_key": key,
        "max_duration": max_duration
    }

    if first_name:
        params["first_name"] = first_name
    if last_name:
        params["last_name"] = last_name
    if full_name:
        params["full_name"] = full_name
    if domain:
        params["domain"] = domain
    if company:
        params["company"] = company

    response = requests.get(HUNTER_EMAIL_FINDER_URL, params=params, timeout=30)

    try:
        data = response.json()
    except Exception:
        response.raise_for_status()
        data = {"status_code": response.status_code, "raw_response": response.text}

    return data
