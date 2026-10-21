"""Unit tests for the RSA helpers and the public key extraction."""

from __future__ import annotations

import base64

import pytest

from felicity_client.crypto import (
    DEFAULT_PUBLIC_KEY_B64,
    PublicKeyExtractionError,
    collect_asset_urls,
    encrypt_password,
    extract_public_key_b64,
    public_key_fingerprint,
    render_pem,
)


class TestEncryptPassword:
    def test_produces_base64_ciphertext(self) -> None:
        ciphertext = encrypt_password("hunter2")
        # 256 bytes of RSA payload, base64-encoded.
        assert len(base64.b64decode(ciphertext)) == 256

    def test_is_not_deterministic(self) -> None:
        """PKCS#1 v1.5 uses random padding, so two runs must differ."""
        assert encrypt_password("hunter2") != encrypt_password("hunter2")

    def test_never_leaks_the_plaintext(self) -> None:
        ciphertext = encrypt_password("s3cr3t-p4ssw0rd")
        assert "s3cr3t-p4ssw0rd" not in ciphertext

    def test_rejects_an_invalid_key(self) -> None:
        with pytest.raises(PublicKeyExtractionError):
            encrypt_password("hunter2", "not-a-key")


class TestPublicKeyFingerprint:
    def test_is_stable(self) -> None:
        assert public_key_fingerprint(DEFAULT_PUBLIC_KEY_B64) == public_key_fingerprint(
            DEFAULT_PUBLIC_KEY_B64
        )

    def test_is_a_sha256_hex_string(self) -> None:
        fingerprint = public_key_fingerprint(DEFAULT_PUBLIC_KEY_B64)
        assert len(fingerprint) == 95  # 32 bytes, colon separated
        assert fingerprint.count(":") == 31

    def test_changes_with_the_key(self) -> None:
        other = base64.b64encode(b"x" * 294).decode()
        assert public_key_fingerprint(other) != public_key_fingerprint(DEFAULT_PUBLIC_KEY_B64)


class TestRenderPem:
    def test_produces_a_parseable_pem(self) -> None:
        pem = render_pem(DEFAULT_PUBLIC_KEY_B64)
        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert pem.rstrip().endswith("-----END PUBLIC KEY-----")
        body = pem.split("-----")[2].strip()
        assert base64.b64decode(body) == base64.b64decode(DEFAULT_PUBLIC_KEY_B64)


class TestExtractPublicKey:
    def test_finds_an_inline_key(self) -> None:
        source = f'jsencrypt.setPublicKey("{DEFAULT_PUBLIC_KEY_B64}");'
        assert extract_public_key_b64(source) == DEFAULT_PUBLIC_KEY_B64

    def test_finds_a_key_assigned_to_a_variable(self) -> None:
        source = 'const a="x";setPublicKey(a);a="' + DEFAULT_PUBLIC_KEY_B64 + '";export default a;'
        assert extract_public_key_b64(source) == DEFAULT_PUBLIC_KEY_B64

    def test_picks_the_longest_assignment_to_the_same_variable(self) -> None:
        """A variable assigned twice keeps the longest (i.e. the key) value."""
        source = 'setPublicKey(key);key="short";key="' + DEFAULT_PUBLIC_KEY_B64 + '";'
        assert extract_public_key_b64(source) == DEFAULT_PUBLIC_KEY_B64

    def test_ignores_a_short_assignment_to_the_variable(self) -> None:
        """A variable that is never assigned a key-sized value is not a key."""
        source = 'setPublicKey(key);key="short";'
        with pytest.raises(PublicKeyExtractionError):
            extract_public_key_b64(source)

    def test_raises_when_no_key_is_present(self) -> None:
        with pytest.raises(PublicKeyExtractionError, match="setPublicKey"):
            extract_public_key_b64("console.log('nothing to see here')")

    def test_ignores_a_non_base64_literal(self) -> None:
        with pytest.raises(PublicKeyExtractionError):
            extract_public_key_b64('setPublicKey("not-a-key");')


class TestCollectAssetUrls:
    def test_finds_script_tags(self) -> None:
        html = '<html><head><script src="/assets/index.abc123.js"></script></head></html>'
        assert collect_asset_urls(html) == ["/assets/index.abc123.js"]

    def test_finds_bundle_references(self) -> None:
        source = 'import x from "/assets/chunk.def456.js";'
        assert collect_asset_urls(source) == ["/assets/chunk.def456.js"]

    def test_deduplicates(self) -> None:
        html = '<script src="/assets/a.js"></script><script src="/assets/a.js"></script>'
        assert collect_asset_urls(html) == ["/assets/a.js"]
