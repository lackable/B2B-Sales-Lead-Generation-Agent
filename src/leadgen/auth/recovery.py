"""Recovery codes: 100 bits of entropy, displayed once, stored as a hash.

Format: ``K7Q2-9XMP-4HDA-ZR8N-TW3C`` — five groups of four symbols from the
Crockford base32 alphabet (32 symbols), which is exactly ``20 * log2(32) = 100``
bits. It omits ``I``, ``L``, ``O`` and ``U`` so a handwritten code stays
unambiguous, and ``normalize_recovery_code`` maps the look-alikes back.
"""

import secrets
import unicodedata

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
GROUP_SIZE = 4
GROUP_COUNT = 5
CODE_LENGTH = GROUP_SIZE * GROUP_COUNT

# Typed-by-hand look-alikes → the symbol they meant (Crockford decoding rules).
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def generate_recovery_code() -> str:
    """A new formatted recovery code, e.g. ``K7Q2-9XMP-4HDA-ZR8N-TW3C``."""
    symbols = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(symbols[offset : offset + GROUP_SIZE] for offset in range(0, CODE_LENGTH, GROUP_SIZE))


def normalize_recovery_code(code: str) -> str:
    """Uppercase, drop separators and fold look-alikes so ``k7q2 9xmp…`` verifies."""
    cleaned = "".join(character for character in unicodedata.normalize("NFKC", code or "") if character.isalnum())
    return cleaned.upper().translate(_LOOKALIKES)


def is_well_formed(code: str) -> bool:
    """True when the code has the expected shape and alphabet."""
    normalized = normalize_recovery_code(code)
    return len(normalized) == CODE_LENGTH and all(symbol in ALPHABET for symbol in normalized)
