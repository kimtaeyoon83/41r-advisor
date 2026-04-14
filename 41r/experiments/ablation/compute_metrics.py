"""Ablation 메트릭 1·2·5 자동 계산.

메트릭 1: A/B 승자 예측 정확도 (이미 run_ablation.py에서 계산)
메트릭 2: 세그먼트 분기 감지율 (이미 계산)
메트릭 5: 반직관적 케이스(Groove, EA) 탐지 명확성
  - 각 페르소나 예측의 확신도 × 방향성
  - 반직관적 케이스에서 얼마나 강한 의견 분기를 보이는가
"""

import json
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE.parent.parent))

_RESULTS = _BASE / "results_ablation.json"
_METRICS_OUT = _BASE / "metrics_computed.json"

# 반직관적 케이스 (CRO 상식과 반대로 간 케이스)
COUNTERINTUITIVE_CASES = {"groove_pricing", "ea_simcity_promo"}


def compute_case_divergence_score(evals: list[dict]) -> float:
    """한 케이스의 페르소나 의견 분기 강도.

    확신도 가중. 양쪽 투표가 비슷할수록 점수 높음 (분기 강함).
    0 = 전원 동의, 1 = 극단적 50:50 분기
    """
    a_score = sum(e.get("confidence", 0) for e in evals if e.get("predicted_winner") == "A")
    b_score = sum(e.get("confidence", 0) for e in evals if e.get("predicted_winner") == "B")
    total = a_score + b_score
    if total == 0:
        return 0.0
    # min/max 비율 → 비슷할수록 1에 가까움
    return min(a_score, b_score) / max(a_score, b_score) if max(a_score, b_score) > 0 else 0.0


def compute_metrics(data: dict) -> dict:
    arm_a = data["arm_a_results"]
    arm_b = data["arm_b_results"]

    # 케이스별 짝지어 비교
    case_comparison = []
    for ra, rb in zip(arm_a, arm_b):
        ca_div = compute_case_divergence_score(ra["persona_evaluations"])
        cb_div = compute_case_divergence_score(rb["persona_evaluations"])
        case_comparison.append({
            "case_id": ra["case_id"],
            "company": ra["company"],
            "actual_winner": ra["actual_winner"],
            "lift_pct": ra["lift_pct"],
            "is_counterintuitive": ra["case_id"] in COUNTERINTUITIVE_CASES,
            "arm_a": {
                "predicted": ra["predicted_winner"],
                "match": ra["match"],
                "divergence_score": round(ca_div, 3),
                "votes": _vote_summary(ra["persona_evaluations"]),
            },
            "arm_b": {
                "predicted": rb["predicted_winner"],
                "match": rb["match"],
                "divergence_score": round(cb_div, 3),
                "votes": _vote_summary(rb["persona_evaluations"]),
            },
        })

    # 집계
    total = len(case_comparison)
    arm_a_correct = sum(1 for c in case_comparison if c["arm_a"]["match"])
    arm_b_correct = sum(1 for c in case_comparison if c["arm_b"]["match"])

    # 메트릭 2: 분기 감지 (confidence-weighted)
    avg_div_a = sum(c["arm_a"]["divergence_score"] for c in case_comparison) / total
    avg_div_b = sum(c["arm_b"]["divergence_score"] for c in case_comparison) / total

    # 메트릭 5: 반직관 케이스 성능
    counterintuitive = [c for c in case_comparison if c["is_counterintuitive"]]
    ci_a_correct = sum(1 for c in counterintuitive if c["arm_a"]["match"])
    ci_b_correct = sum(1 for c in counterintuitive if c["arm_b"]["match"])
    ci_a_div = sum(c["arm_a"]["divergence_score"] for c in counterintuitive) / len(counterintuitive) if counterintuitive else 0
    ci_b_div = sum(c["arm_b"]["divergence_score"] for c in counterintuitive) / len(counterintuitive) if counterintuitive else 0

    # 케이스별 우승자 (어느 arm이 더 나았는가)
    b_strictly_better = sum(
        1 for c in case_comparison
        if c["arm_b"]["match"] and not c["arm_a"]["match"]
    )
    a_strictly_better = sum(
        1 for c in case_comparison
        if c["arm_a"]["match"] and not c["arm_b"]["match"]
    )

    return {
        "metric_1_accuracy": {
            "arm_a_pct": round(arm_a_correct / total * 100, 1),
            "arm_b_pct": round(arm_b_correct / total * 100, 1),
            "delta_pp": round((arm_b_correct - arm_a_correct) / total * 100, 1),
            "b_strictly_better_cases": b_strictly_better,
            "a_strictly_better_cases": a_strictly_better,
        },
        "metric_2_divergence": {
            "arm_a_avg_score": round(avg_div_a, 3),
            "arm_b_avg_score": round(avg_div_b, 3),
            "delta": round(avg_div_b - avg_div_a, 3),
            "description": "0=전원동의, 1=극단분기. 확신도 가중.",
        },
        "metric_5_counterintuitive": {
            "cases": list(COUNTERINTUITIVE_CASES),
            "arm_a_correct": f"{ci_a_correct}/{len(counterintuitive)}",
            "arm_b_correct": f"{ci_b_correct}/{len(counterintuitive)}",
            "arm_a_avg_divergence": round(ci_a_div, 3),
            "arm_b_avg_divergence": round(ci_b_div, 3),
        },
        "case_comparison": case_comparison,
    }


def _vote_summary(evals: list[dict]) -> dict:
    votes = {"A": 0, "B": 0}
    for e in evals:
        w = e.get("predicted_winner")
        if w in votes:
            votes[w] += 1
    return votes


def main():
    with open(_RESULTS) as f:
        data = json.load(f)

    metrics = compute_metrics(data)

    with open(_METRICS_OUT, "w") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # 요약 출력
    print("=" * 70)
    print("METRIC 1: Accuracy")
    print(f"  Arm A: {metrics['metric_1_accuracy']['arm_a_pct']}%")
    print(f"  Arm B: {metrics['metric_1_accuracy']['arm_b_pct']}%")
    print(f"  Delta: {metrics['metric_1_accuracy']['delta_pp']:+.1f}%p")
    print(f"  B strictly better in: {metrics['metric_1_accuracy']['b_strictly_better_cases']} cases")
    print(f"  A strictly better in: {metrics['metric_1_accuracy']['a_strictly_better_cases']} cases")
    print()
    print("METRIC 2: Divergence Score (confidence-weighted)")
    print(f"  Arm A: {metrics['metric_2_divergence']['arm_a_avg_score']}")
    print(f"  Arm B: {metrics['metric_2_divergence']['arm_b_avg_score']}")
    print(f"  Delta: {metrics['metric_2_divergence']['delta']:+.3f}")
    print()
    print("METRIC 5: Counterintuitive Cases")
    ci = metrics["metric_5_counterintuitive"]
    print(f"  Cases: {ci['cases']}")
    print(f"  Arm A correct: {ci['arm_a_correct']}, divergence: {ci['arm_a_avg_divergence']}")
    print(f"  Arm B correct: {ci['arm_b_correct']}, divergence: {ci['arm_b_avg_divergence']}")
    print()
    print("CASE-BY-CASE:")
    for c in metrics["case_comparison"]:
        marker_a = "✓" if c["arm_a"]["match"] else "✗"
        marker_b = "✓" if c["arm_b"]["match"] else "✗"
        ci_marker = " [CI]" if c["is_counterintuitive"] else ""
        print(f"  {c['case_id']:30s} | A: {marker_a} div={c['arm_a']['divergence_score']:.2f} | B: {marker_b} div={c['arm_b']['divergence_score']:.2f}{ci_marker}")

    print(f"\nSaved: {_METRICS_OUT}")


if __name__ == "__main__":
    main()
