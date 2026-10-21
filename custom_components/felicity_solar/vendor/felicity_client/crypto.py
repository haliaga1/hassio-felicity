"""RSA password encryption and public-key discovery for the FSolar login.

The FSolar web app encrypts the account password with a 2048-bit RSA public
key (PKCS#1 v1.5) before posting it to ``/userlogin``. The key lives in the
login bundle of the web app.

Two strategies are implemented:

* the key is **embedded** as a constant, which is the fast path;
* if the backend rejects the ciphertext, the key is **re-extracted live** from
  the login page, because the vendor may rotate it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

__all__ = [
    "DEFAULT_PUBLIC_KEY_B64",
    "PublicKeyExtractionError",
    "encrypt_password",
    "extract_public_key_b64",
    "public_key_fingerprint",
    "render_pem",
]

#: 2048-bit RSA public key (SPKI, base64) used by the FSolar web app.
DEFAULT_PUBLIC_KEY_B64: Final = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnAJE68pjWZmtSg6ZJs9FZugJXC6bBSluTW6mJ"
    "ttOLOaljrdErVnM5DNN+YFzpB9pAysTErjY1bnSVuEwQSwptnqUji7Ch2qMj2n+0eCp8p6vtSh7/tFr2ul"
    "8nDRtkoswLANAIwtUk/G85ipMpmY1W642LImnEJmGkkddlbjbjxJTZWR5hc/d9cPWb+AR77LxFFrMik3c"
    "+44v1kQlIPFP6EjIbOvt/Lv7fHWD9JI/YzN4y1gK7C/VQdNGuikQyNg+5W3rg9ecYf9I5uLAQwY/hxeI3l"
    "bNsErebqKe2EbJ8AwcNIC0lDBz53Sq0ML89QapEuy3fB+upuctxLULVDCbNwIDAQAB"
)

#: Matches ``<script src="...index.<hash>.js">`` style asset references.
_ASSET_RE = re.compile(
    r"""(?:src|href)\s*=\s*["']([^"']*?/assets/[^"']*?\.js)["']""",
    re.IGNORECASE,
)

#: Matches a bare ``/assets/...js`` reference inside a JS bundle.
_BUNDLE_ASSET_RE = re.compile(r"""["'](/assets/[^"']*?\.js)["']""")

#: Matches ``setPublicKey(<identifier>)`` and ``setPublicKey("<base64>")``.
_SET_PUBLIC_KEY_RE = re.compile(
    r"""setPublicKey\s*\(\s*(?:(["'])(?P<literal>[A-Za-z0-9+/=]+)\1|(?P<var>[A-Za-z0-9_$]+))"""
)

#: Matches ``<var> = "<base64>"`` and ``var="<base64>"``.
_ASSIGNMENT_RE = re.compile(
    r"""(?P<var>[A-Za-z0-9_$]+)\s*=\s*(?P<quote>["'`])(?P<value>[A-Za-z0-9+/=]{200,})(?P=quote)"""
)


class PublicKeyExtractionError(RuntimeError):
    """The RSA public key could not be located in the web app bundle."""


@dataclass(frozen=True, slots=True)
class ExtractedKey:
    """A public key recovered from the web app, with provenance."""

    b64: str
    source: str

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the key, for drift detection."""
        return public_key_fingerprint(self.b64)


def render_pem(public_key_b64: str) -> str:
    """Wrap a bare base64 SPKI blob in PEM armour."""
    body = "\n".join(public_key_b64[i : i + 64] for i in range(0, len(public_key_b64), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{body}\n-----END PUBLIC KEY-----\n"


def public_key_fingerprint(public_key_b64: str) -> str:
    """Return the SHA-256 fingerprint of a base64 SPKI public key."""
    digest = hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2)).upper()


def _load_public_key(public_key_b64: str) -> rsa.RSAPublicKey:
    try:
        raw = base64.b64decode(public_key_b64)
    except (binascii.Error, ValueError) as exc:
        raise PublicKeyExtractionError(f"public key is not valid base64: {exc}") from exc
    try:
        key = serialization.load_der_public_key(raw)
    except Exception as exc:
        raise PublicKeyExtractionError(f"public key is not a valid SPKI blob: {exc}") from exc
    if not isinstance(key, rsa.RSAPublicKey):
        raise PublicKeyExtractionError(f"expected an RSA key, got {type(key).__name__}")
    return key


def encrypt_password(password: str, public_key_b64: str = DEFAULT_PUBLIC_KEY_B64) -> str:
    """Encrypt a password the way the FSolar web app does.

    Uses RSA PKCS#1 v1.5 with the SPKI public key and returns the base64
    ciphertext expected by ``POST /userlogin``.
    """
    key = _load_public_key(public_key_b64)
    ciphertext = key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(ciphertext).decode("ascii")


def extract_public_key_b64(*javascript_sources: str) -> str:
    """Recover the RSA public key from one or more JavaScript sources.

    Handles both shapes used by the web app:

    * ``setPublicKey("<base64>")`` — the key inline;
    * ``setPublicKey(someVar)`` followed by ``someVar = "<base64>"``.
    """
    combined = "\n".join(javascript_sources)

    for match in _SET_PUBLIC_KEY_RE.finditer(combined):
        literal = match.group("literal")
        if literal and _looks_like_key(literal):
            return literal

        var_name = match.group("var")
        if not var_name:
            continue
        escaped = re.escape(var_name)
        assignment = re.compile(rf"""{escaped}\s*=\s*(["'`])(?P<value>[A-Za-z0-9+/=]{{200,}})\1""")
        candidates = [m.group("value") for m in assignment.finditer(combined)]
        if candidates:
            # The bundle may contain several assignments; the key is by far
            # the longest one.
            return max(candidates, key=len)

    raise PublicKeyExtractionError(
        "no setPublicKey() call found in the supplied JavaScript sources; "
        "the FSolar web app layout may have changed"
    )


def collect_asset_urls(html_or_js: str) -> list[str]:
    """Return the JS asset URLs referenced by a page or bundle."""
    urls: list[str] = []
    for pattern in (_ASSET_RE, _BUNDLE_ASSET_RE):
        for match in pattern.finditer(html_or_js):
            urls.append(match.group(1))
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _looks_like_key(value: str) -> bool:
    """A 2048-bit SPKI key in base64 is 392 characters long."""
    if len(value) < 300:
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) > 200


def key_metadata(public_key_b64: str) -> dict[str, str | int]:
    """Return descriptive metadata about a public key (for diagnostics)."""
    key = _load_public_key(public_key_b64)
    public_numbers = key.public_numbers()
    return {
        "key_size": key.key_size,
        "exponent": public_numbers.e,
        "fingerprint_sha256": public_key_fingerprint(public_key_b64),
        "algorithm": "RSA",
        "digest": hashes.SHA256().name,
    }
