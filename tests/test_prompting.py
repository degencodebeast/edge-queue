from edgequeue.corpus import build_development_cases
from edgequeue.prompting import render_case_assessment_prompt


def test_renders_only_ranker_visible_case_content() -> None:
    case = build_development_cases()[0]

    prompt = render_case_assessment_prompt(case.ranker_case)

    assert "EQ-F01-DEV-01" in prompt
    assert "Current Verdict: FAIL" in prompt
    assert "E3 artifact" in prompt
    assert "reference_verdict" not in prompt
    assert "SCORER_ONLY" not in prompt
