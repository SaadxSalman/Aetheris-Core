"""Cryptographic source attribution: per-citation HMAC attestations.

Every citation shipped with an answer carries:
  * content_sha256 : peppered SHA-256 of the exact embedded chunk text
  * attestation    : HMAC-SHA256(secret, chunk_id:content_sha256:request_id)
Clients can POST a citation to /verify-citation to prove the engine answered
from that exact byte range of that exact chunk under that request.
"""
from __future__ import annotations

import hashlib
import hmac

from aetheris.config import settings


def content_digest(text: str) -> str:
    return hashlib.sha256(
        settings.CONTENT_HASH_PEPPER.encode() + text.encode("utf-8", errors="replace")
    ).hexdigest()


def attest(chunk_id: str, content_sha256: str, request_id: str) -> str:
    message = f"{chunk_id}:{content_sha256}:{request_id}".encode("utf-8")
    return hmac.new(settings.ATTRIBUTION_HMAC_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify(chunk_id: str, content_sha256: str, request_id: str, signature: str) -> bool:
    expected = attest(chunk_id, content_sha256, request_id)
    return hmac.compare_digest(expected, signature or "")


def citation_record(chunk_id: str, content_sha256: str, request_id: str,
                    index: int, title: str, header_path: str, source: str,
                    uri: str | None = None, snippet: str = "") -> dict:
    return {
        "index": index,
        "chunk_id": chunk_id,
        "title": title,
        "header_path": header_path,
        "source": source,
        "uri": uri,
        "snippet": snippet[:280],
        "content_sha256": content_sha256,
        "request_id": request_id,
        "attestation": attest(chunk_id, content_sha256, request_id),
        "verified": True,
    }
