#!/usr/bin/env python
"""
Hunter.io LinkedIn Email Finder — standalone CLI.

Library logic lives in ``leadgen.core.clients.hunter``; this is the thin CLI on top.

Examples::

    python scripts/find_email.py -l "https://www.linkedin.com/in/alexisohanian/"
    python scripts/find_email.py -l alexisohanian --domain reddit.com --json
"""

import argparse
import json
import sys
from typing import Any, Dict

from leadgen.core.clients.hunter import find_email_by_linkedin, get_hunter_api_key


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
        return "API Error Response:\n" + "\n".join(error_msgs)
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
