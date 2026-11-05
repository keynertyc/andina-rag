from unittest.mock import Mock

from app.errors import AppError

from scripts.evaluate import run_cases, select_threshold, summarize


def test_calibration_preserves_expected_evidence_not_just_any_chunk():
    cases = [{"product": {"id": "p"}, "should_block": False, "expected_rule": "DESCRIPTION"}]
    context = {
        "p": [{"text": "TITLE", "similarity": 0.91}, {"text": "DESCRIPTION", "similarity": 0.82}]
    }
    threshold, _ = select_threshold(cases, context)
    assert threshold == 0.8


def test_provider_failure_does_not_count_as_correct_evidence_block(monkeypatch, product):
    monkeypatch.setattr(
        "scripts.evaluate.generate_validated",
        Mock(side_effect=AppError("BAD_OUTPUT", "bad output")),
    )
    cases = [{"product": product.model_dump(), "should_block": True, "expected_rule": None}]
    rows = run_cases(
        cases, {product.id: [{"id": "c1", "text": "wrong evidence", "similarity": 0.9}]}, 0.8
    )
    assert not rows[0]["blocked"] and rows[0]["error"] == "AppError"
    assert summarize(rows)["correct_insufficient_evidence_blocking"] == 0
