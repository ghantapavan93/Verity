"""The one place that turns content into identity.

Documents, guidance, prompts, memo files and run fingerprints are all hashed here, so a change
to how identity is computed is a change in one file with one set of tests. Nothing else in the
application imports hashlib; a test scans `app/` for it. The evidence pack's standalone
`verify.py` and two scripts hash on their own because they run outside the application.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

ALGORITHM = "sha256"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """UTF-8 bytes of the text as given. Callers normalise (strip, newline policy) before hashing."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def mac_sha256(key: str, message: str) -> str:
    """HMAC-SHA256 of the message under the key: what makes an invite or a session token one this server issued
    (api.access). Compare with `hmac.compare_digest`, never with `==`."""
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def fingerprint(kind: str, *parts: str | None) -> str:
    """A stable identity for a tuple of strings.

    Each part is length-prefixed so that ("ab", "c") and ("a", "bc") never collide, and None is
    distinguishable from the empty string. ``kind`` names the schema of the tuple (for example
    "run/v1") so a later change in what goes into a fingerprint changes every fingerprint.
    """
    encoded = [kind.encode("utf-8")]
    for part in parts:
        if part is None:
            encoded.append(b"-")
        else:
            data = part.encode("utf-8")
            encoded.append(f"{len(data)}:".encode("ascii") + data)
    return sha256_bytes(b"\x1f".join(encoded))
