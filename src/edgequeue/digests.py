"""Canonical content digests for frozen EdgeQueue artifacts."""

from __future__ import annotations

from collections.abc import Set
from typing import Any

from edgequeue.contracts import (
    NON_AUTHORITATIVE_TIMESTAMP_FIELDS,
    canonical_json,
    content_digest as _content_digest,
)


def content_digest(
    payload: Any,
    *,
    excluded_keys: Set[str] = NON_AUTHORITATIVE_TIMESTAMP_FIELDS,
) -> str:
    """Return the SHA-256 digest of a canonical JSON payload."""
    return _content_digest(payload, excluded_keys=excluded_keys)


__all__ = ["canonical_json", "content_digest"]
