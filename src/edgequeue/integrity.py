import json
from typing import Any, AbstractSet


class ScorerLeakageDetected(ValueError):
    """Allocator-visible artifacts contain scorer-only content."""


def reject_scorer_leakage(
    allocator_artifacts: Any,
    *,
    forbidden_field_names: AbstractSet[str],
    scorer_sentinels: AbstractSet[str],
) -> None:
    serialized_artifacts = json.dumps(
        allocator_artifacts,
        ensure_ascii=False,
        sort_keys=True,
    )
    forbidden_terms = forbidden_field_names | scorer_sentinels
    matches = sorted(term for term in forbidden_terms if term in serialized_artifacts)

    if matches:
        raise ScorerLeakageDetected(
            f"Scorer-only content found: {', '.join(matches)}"
        )
