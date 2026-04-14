"""Hallucination Guard 핵심 함수 테스트."""
import json
import tempfile
from pathlib import Path

import pytest

from modules import hallucination_guard


def test_flatten_json_simple():
    data = {"a": 1, "b": {"c": 2.5}}
    flat = hallucination_guard._flatten_json(data)
    assert flat == {"a": 1.0, "b.c": 2.5}


def test_flatten_json_with_list():
    data = {"items": [1, 2, 3]}
    flat = hallucination_guard._flatten_json(data)
    assert flat == {"items[0]": 1.0, "items[1]": 2.0, "items[2]": 3.0}


def test_flatten_json_nested():
    data = {"a": {"b": {"c": [10, 20]}}}
    flat = hallucination_guard._flatten_json(data)
    assert flat == {"a.b.c[0]": 10.0, "a.b.c[1]": 20.0}


def test_is_close_match_exact():
    assert hallucination_guard._is_close_match(0.5, {0.5})


def test_is_close_match_within_tol():
    assert hallucination_guard._is_close_match(0.51, {0.5}, tol=0.02)


def test_is_close_match_sign_invariant():
    assert hallucination_guard._is_close_match(0.575, {-0.575})


def test_is_close_match_far():
    assert not hallucination_guard._is_close_match(99.0, {0.5, 1.0})


def test_check_ratio_simple():
    # 0.604 / 0.282 ≈ 2.142
    truth_values = {0.282, 0.604}
    assert hallucination_guard._check_ratio(2.14, truth_values, tol=0.02)


def test_strip_html_basic():
    html = "<div><p>Hello <b>world</b></p></div>"
    text = hallucination_guard._strip_html(html)
    assert "Hello" in text
    assert "<" not in text


def test_audit_numbers_finds_unmatched(tmp_path):
    # Ground truth: 0.5만 있음
    gt_dir = tmp_path / "gt"
    gt_dir.mkdir()
    (gt_dir / "data.json").write_text(json.dumps({"value": 0.5}))

    # Report: 0.5와 99.99
    report_path = tmp_path / "report.md"
    report_path.write_text("값은 0.5인데, 99.99라는 주장도 있음.")

    findings = hallucination_guard.audit_numbers(str(report_path), [str(gt_dir)])
    # 99.99는 매치 안 됨
    assert any("99.99" in f.claim for f in findings)
    # 0.5는 매치됨 (안전 목록일 수 있으니 약하게)


def test_find_sources_returns_path_field(tmp_path):
    truth = {
        "/some/path/data.json": {
            "conversion_rate": 0.3,
            "engagement.avg_turns": 9.06,
        }
    }
    sources = hallucination_guard._find_sources(0.3, truth)
    assert len(sources) >= 1
    # 첫 매치는 정확값
    p, f, v, q = sources[0]
    assert v == 0.3
    assert "exact" in q


def test_recompute_pvalue_binomial(tmp_path):
    # binomial test 12/12 one-tailed
    data_path = tmp_path / "metric.json"
    data_path.write_text(json.dumps({
        "head_to_head": {"arm_b_wins": 12},
        "total_cases": 12,
    }))
    spec = {
        "data_path": str(data_path),
        "type": "binomial",
        "field_k": "head_to_head.arm_b_wins",
        "field_n": "total_cases",
        "alternative": "greater",
    }
    p = hallucination_guard._recompute_pvalue(spec)
    assert p is not None
    assert abs(p - 0.000244) < 1e-5


def test_recompute_pvalue_fisher(tmp_path):
    # Fisher's exact 11/12 vs 10/12 → p≈1.0
    data_path = tmp_path / "metric.json"
    data_path.write_text(json.dumps({
        "a": 11, "b": 1, "c": 10, "d": 2,
    }))
    spec = {
        "data_path": str(data_path),
        "type": "fisher",
        "field_a": "a", "field_b": "b", "field_c": "c", "field_d": "d",
    }
    p = hallucination_guard._recompute_pvalue(spec)
    assert p is not None
    assert p > 0.99


# === Claim Tagging 검증 ===

def test_audit_tagged_claims_match(tmp_path):
    """태그된 src와 실제 값이 일치하면 OK."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({"conversion_rate": 0.30, "n_total": 20}))

    report = tmp_path / "report.html"
    report.write_text(
        f'전환율: <span data-src="{src_data}:conversion_rate">30%</span>'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    # critical 없어야 함
    assert not any(f.severity == "critical" for f in findings)


def test_audit_tagged_claims_mismatch_detected(tmp_path):
    """태그된 src와 표시값 불일치 시 critical."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({"conversion_rate": 0.30}))

    report = tmp_path / "report.html"
    report.write_text(
        f'<span data-src="{src_data}:conversion_rate">99%</span>'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    assert any(f.severity == "critical" for f in findings)


def test_audit_tagged_claims_missing_field(tmp_path):
    """src field가 ground truth에 없으면 critical."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({"a": 1}))

    report = tmp_path / "report.html"
    report.write_text(
        f'<span data-src="{src_data}:nonexistent_field">10</span>'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    assert any(f.severity == "critical" for f in findings)


def test_audit_tagged_claims_nested_field(tmp_path):
    """중첩 필드 (a.b.c) 추적."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({
        "engagement": {"avg_turns": 9.06}
    }))

    report = tmp_path / "report.html"
    report.write_text(
        f'<span data-src="{src_data}:engagement.avg_turns">9.06</span>'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    assert not any(f.severity == "critical" for f in findings)


def test_audit_tagged_claims_md_format(tmp_path):
    """Markdown 형식: [표시값]{src=path:field}."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({"score": 4.83}))

    report = tmp_path / "report.md"
    report.write_text(
        f'블라인드 점수 [4.83]{{src={src_data}:score}}'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    assert not any(f.severity == "critical" for f in findings)


def test_audit_tagged_claims_percentage_conversion(tmp_path):
    """0.3 vs 30% 자동 변환 매칭."""
    src_data = tmp_path / "agg.json"
    src_data.write_text(json.dumps({"rate": 0.3}))

    report = tmp_path / "report.html"
    report.write_text(
        f'<span data-src="{src_data}:rate">30%</span>'
    )

    findings = hallucination_guard.audit_tagged_claims(str(report))
    assert not any(f.severity == "critical" for f in findings)
