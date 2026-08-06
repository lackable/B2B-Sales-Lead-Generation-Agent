"""
Redaction utility: walks a dict recursively and replaces the *values* of any key
whose name matches the API-key / secret pattern with "***".

Pattern matches (case-insensitive):
  api_key  api-key  apikey  token  secret
"""

import re
from typing import Any

_SENSITIVE_KEY_RE = re.compile(r"api[_-]?key|apikey|token|secret", re.IGNORECASE)


def redact(data: Any) -> Any:
    """Return a deep copy of *data* with sensitive values replaced by '***'."""
    if isinstance(data, dict):
        return {k: ("***" if _SENSITIVE_KEY_RE.search(str(k)) else redact(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact(item) for item in data]
    return data
