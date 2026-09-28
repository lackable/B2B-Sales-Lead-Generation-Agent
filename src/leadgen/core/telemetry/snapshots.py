"""Sanitized authoritative snapshots for frontend synchronization."""


def sanitize_decision_makers(decision_makers: list[dict]) -> list[dict]:
    """Keep final names and roles while excluding URLs and other contact data."""
    return [
        {
            "name": str(contact.get("name") or "").strip(),
            "role": str(
                contact.get("position")
                or contact.get("role")
                or contact.get("title")
                or ""
            ).strip(),
        }
        for contact in decision_makers
    ]
