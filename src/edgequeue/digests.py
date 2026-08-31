"""Canonical content digests for frozen EdgeQueue artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Set
from typing import Any


def content_digest(payload: Any, *, excluded_keys: Set[str] = frozenset()) -> str:
    """Return the SHA-256 digest of a canonical JSON payload."""
    canonical_payload = _canonicalize(payload, excluded_keys=excluded_keys)
    canonical_json = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _canonicalize(value: Any, *, excluded_keys: Set[str]) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _canonicalize(item, excluded_keys=excluded_keys)
            for key, item in value.items()
            if key not in excluded_keys
        }
    if isinstance(value, list):
        return [_canonicalize(item, excluded_keys=excluded_keys) for item in value]
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    return value
