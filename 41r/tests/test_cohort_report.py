"""Cohort Report 집계 함수 테스트."""
import math

from modules import cohort_report


def test_wilson_ci_zero_n():
    lo, hi = cohort_report._wilson_ci(0, 0)
    assert lo == 0.0 and hi == 0.0


def test_wilson_ci_all_success():
    lo, hi = cohort_report._wilson_ci(20, 20)
    assert hi == 1.0 or hi > 0.85
    assert lo > 0.7  # 20/20 → 95% CI 하한 ~0.83


def test_wilson_ci_mid():
    lo, hi = cohort_report._wilson_ci(6, 20)
    # 30% 전환율 → CI 약 14~52%
    assert 0.10 < lo < 0.20
    assert 0.45 < hi < 0.60


def test_classify_outcome():
    assert cohort_report._classify_outcome("task_complete") == "converted"
    assert cohort_report._classify_outcome("abandoned") == "abandoned"
    assert cohort_report._classify_outcome("max_turns_hit") == "partial"
    assert cohort_report._classify_outcome("error") == "abandoned"
    assert cohort_report._classify_outcome("unknown_state") == "unknown"


def test_pearson_perfect_correlation():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2, 4, 6, 8, 10]
    r = cohort_report._pearson(x, y)
    assert abs(r - 1.0) < 0.001


def test_pearson_no_correlation():
    x = [1.0, 2.0, 3.0]
    y = [1, 1, 1]  # variance 0
    r = cohort_report._pearson(x, y)
    assert r == 0.0


def test_aggregate_cohort_basic():
    cohort_result = {
        "results": [
            {"outcome": "task_complete", "predicted_turns": 5, "conversion_probability": 0.8,
             "persona_traits": {"impulsiveness": 0.8}},
            {"outcome": "task_complete", "predicted_turns": 7, "conversion_probability": 0.7,
             "persona_traits": {"impulsiveness": 0.6}},
            {"outcome": "abandoned", "predicted_turns": 2, "conversion_probability": 0.1,
             "persona_traits": {"impulsiveness": 0.2}},
        ],
    }
    agg = cohort_report.aggregate_cohort(cohort_result)
    assert agg["n_total"] == 3
    assert agg["n_converted"] == 2
    assert agg["n_abandoned"] == 1
    assert abs(agg["conversion_rate"] - 0.667) < 0.01
    # impulsiveness가 conversion_probability와 양의 상관
    corrs = agg["trait_outcome_correlations"]
    assert corrs.get("impulsiveness", 0) > 0.5


def test_aggregate_cohort_empty():
    agg = cohort_report.aggregate_cohort({"results": []})
    assert "error" in agg


def test_aggregate_cohort_all_same_outcome():
    cohort_result = {
        "results": [
            {"outcome": "task_complete", "predicted_turns": 5, "conversion_probability": 0.5,
             "persona_traits": {"impulsiveness": 0.5}},
            {"outcome": "task_complete", "predicted_turns": 6, "conversion_probability": 0.4,
             "persona_traits": {"impulsiveness": 0.6}},
        ],
    }
    agg = cohort_report.aggregate_cohort(cohort_result)
    assert agg["conversion_rate"] == 1.0
    # outcome variance=0이지만 conversion_probability variance>0 → 상관 계산됨
    corrs = agg["trait_outcome_correlations"]
    # _target이 conversion_probability여야 함
    assert corrs.get("_target") == "conversion_probability" or "note" in corrs
