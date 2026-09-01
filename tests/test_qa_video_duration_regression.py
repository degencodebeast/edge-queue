import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_submission_validator():
    spec = importlib.util.spec_from_file_location(
        "verify_submission",
        PROJECT_ROOT / "scripts/verify_submission.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_submission_validator_accepts_a_shorter_video_plan() -> None:
    validator = load_submission_validator()

    assert validator.duration_at_or_below_five_minutes("Target duration: 3 minutes 10 seconds.")
    assert validator.duration_at_or_below_five_minutes("Target duration: 5 minutes 0 seconds.")
    assert not validator.duration_at_or_below_five_minutes("Target duration: 5 minutes 1 second.")
    assert not validator.duration_at_or_below_five_minutes("No duration is declared.")
