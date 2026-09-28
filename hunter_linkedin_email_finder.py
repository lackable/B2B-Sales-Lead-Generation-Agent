"""
Hunter.io Email Finder API (v2) - Retrieve Email via LinkedIn Profile/Handle
Documentation: https://hunter.io/api-documentation/v2#email-finder

This script allows you to find a person's email address using their LinkedIn profile URL or handle
via the Hunter.io API.
"""

import os
import re
import sys
import json
import argparse
from typing import Optional, Dict, Any
import requests

import env_config

HUNTER_EMAIL_FINDER_URL = "https://api.hunter.io/v2/email-finder"

def get_hunter_api_key(provided_key: Optional[str] = None) -> Optional[str]:
    """Retrieve API key from argument or environment (root .env via env_config)."""
    return provided_key or env_config.HUNTER_API_KEY


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


def format_result(result: Dict[str, Any]) -> str:
    """Formats the JSON result into a clean, readable text summary."""
    if "data" in result:
        data = result["data"]
        email = data.get("email")
        score = data.get("score")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        position = data.get("position")
        company = data.get("company")
        domain = data.get("domain")
        verification = data.get("verification", {})
        sources = data.get("sources", [])
        linkedin_url = data.get("linkedin_url")

        lines = [
            "=" * 50,
            " HUNTER.IO EMAIL FINDER RESULT",
            "=" * 50,
            f" Full Name    : {first_name or ''} {last_name or ''}".strip(),
            f" Found Email  : {email if email else 'No email found'}",
            f" Confidence   : {score}%" if score is not None else " Confidence   : N/A",
            f" Verification : {verification.get('status', 'N/A')}",
            f" Position     : {position or 'N/A'}",
            f" Company      : {company or 'N/A'} ({domain or 'N/A'})",
            f" LinkedIn URL : {linkedin_url or 'N/A'}",
            f" Sources Count: {len(sources)}"
        ]
        
        if sources:
            lines.append("\n Top Sources:")
            for src in sources[:3]:
                lines.append(f"  - {src.get('uri')} (seen: {src.get('last_seen_on')})")

        lines.append("=" * 50)
        return "\n".join(lines)

    elif "errors" in result:
        errors = result["errors"]
        error_msgs = [f"- {err.get('details', err.get('id', 'Unknown error'))}" for err in errors]
        return f"API Error Response:\n" + "\n".join(error_msgs)
    else:
        return json.dumps(result, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve email of a person through LinkedIn using Hunter.io Email Finder API v2"
    )
    parser.add_argument(
        "-l", "--linkedin",
        required=True,
        help="LinkedIn Profile URL or Handle (e.g. 'https://www.linkedin.com/in/alexisohanian/' or 'alexisohanian')"
    )
    parser.add_argument(
        "-k", "--api-key",
        dest="api_key",
        help="Hunter.io API key (or set HUNTER_API_KEY environment variable)"
    )
    parser.add_argument("--first-name", help="Optional first name")
    parser.add_argument("--last-name", help="Optional last name")
    parser.add_argument("--full-name", help="Optional full name")
    parser.add_argument("--domain", help="Optional company domain (e.g. reddit.com)")
    parser.add_argument("--company", help="Optional company name (e.g. Reddit)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response"
    )

    args = parser.parse_args()

    api_key = get_hunter_api_key(args.api_key)
    if not api_key:
        print("Error: Hunter.io API key not found.", file=sys.stderr)
        print("Please add HUNTER_API_KEY=your_key to the .env file in the repo root,", file=sys.stderr)
        print("or pass --api-key / set HUNTER_API_KEY environment variable.", file=sys.stderr)
        print("You can get a free API key at: https://hunter.io/api-keys", file=sys.stderr)
        sys.exit(1)

    try:
        result = find_email_by_linkedin(
            linkedin_input=args.linkedin,
            api_key=api_key,
            first_name=args.first_name,
            last_name=args.last_name,
            full_name=args.full_name,
            domain=args.domain,
            company=args.company
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_result(result))

    except Exception as err:
        print(f"Error executing Email Finder request: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
