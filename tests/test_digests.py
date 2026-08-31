from edgequeue.digests import content_digest


def test_digest_normalizes_order_line_endings_and_excluded_fields() -> None:
    first = {
        "text": "line1\r\nline2",
        "created_at": "2026-08-31T01:00:00Z",
        "case_id": "case-a",
    }
    second = {
        "case_id": "case-a",
        "created_at": "2026-08-31T02:00:00Z",
        "text": "line1\nline2",
    }

    first_digest = content_digest(first, excluded_keys={"created_at"})
    second_digest = content_digest(second, excluded_keys={"created_at"})

    assert first_digest == second_digest
    assert first_digest == "e165eb0a9d56477c8fa3a33101bbc9c248941f94c3adbae8ec541071b31f2a5d"
