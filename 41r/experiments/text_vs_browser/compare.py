"""Text mode vs Browser mode 결과 비교.

각 사이트의 두 모드 결과를 받아:
- Outcome 분포 일치도
- conversion 확률 분포 비교
- 상관계수 일치도
- 정성적 finding 차이

사용법:
    python -m experiments.text_vs_browser.compare \\
        <site_slug> <text_result.json> <browser_result.json>

또는 일괄:
    python experiments/text_vs_browser/compare.py --auto
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent


def load_result(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def aggregate(result: dict) -> dict:
    """outcome, turns, conversion_prob 분포 추출."""
    results = result.get("results", [])
    outcomes = [r.get("outcome", "?") for r in results]
    turns = [r.get("predicted_turns") or r.get("total_turns") or 0 for r in results]
    turns = [t for t in turns if t > 0]
    probs = [r.get("conversion_probability") for r in results if r.get("conversion_probability") is not None]

    from collections import Counter
    out_counts = Counter(outcomes)

    return {
        "n": len(results),
        "outcome_dist": dict(out_counts),
        "turns_avg": round(statistics.mean(turns), 2) if turns else 0,
        "turns_median": round(statistics.median(turns), 2) if turns else 0,
        "turns_stdev": round(statistics.stdev(turns), 2) if len(turns) > 1 else 0,
        "conv_prob_mean": round(statistics.mean(probs), 3) if probs else None,
        "conv_prob_stdev": round(statistics.stdev(probs), 3) if len(probs) > 1 else 0,
    }


def compare_pair(text_result: dict, browser_result: dict) -> dict:
    """두 결과 비교 — 일치도 점수 계산."""
    t_agg = aggregate(text_result)
    b_agg = aggregate(browser_result)

    # outcome 분포 일치도 (Jaccard-like)
    t_keys = set(t_agg["outcome_dist"].keys())
    b_keys = set(b_agg["outcome_dist"].keys())
    outcome_overlap = len(t_keys & b_keys) / len(t_keys | b_keys) if (t_keys | b_keys) else 0

    # 평균 turn 차이
    turn_diff = abs(t_agg["turns_avg"] - b_agg["turns_avg"])
    turn_match = max(0, 1 - turn_diff / max(t_agg["turns_avg"], b_agg["turns_avg"], 1))

    # conversion 확률 차이
    if t_agg["conv_prob_mean"] is not None and b_agg["conv_prob_mean"] is not None:
        prob_diff = abs(t_agg["conv_prob_mean"] - b_agg["conv_prob_mean"])
        prob_match = max(0, 1 - prob_diff / 0.5)
    else:
        prob_diff = None
        prob_match = None

    overall_score = outcome_overlap * 0.4 + turn_match * 0.3
    if prob_match is not None:
        overall_score += prob_match * 0.3
    else:
        overall_score = overall_score / 0.7

    return {
        "text_aggregate": t_agg,
        "browser_aggregate": b_agg,
        "outcome_distribution_overlap": round(outcome_overlap, 3),
        "turn_avg_diff": round(turn_diff, 2),
        "turn_match_score": round(turn_match, 3),
        "conversion_prob_diff": round(prob_diff, 3) if prob_diff is not None else None,
        "conversion_prob_match_score": round(prob_match, 3) if prob_match is not None else None,
        "overall_consistency_score": round(overall_score, 3),
        "interpretation": _interpret(overall_score),
    }


def _interpret(score: float) -> str:
    if score > 0.8:
        return "높은 일치 — text 예측이 browser 실측과 거의 동일"
    if score > 0.6:
        return "중간 일치 — 방향성은 같지만 수치 차이 있음"
    if score > 0.4:
        return "낮은 일치 — text 예측을 그대로 신뢰하면 위험"
    return "매우 낮은 일치 — 별개 데이터로 취급해야 함"


def auto_compare():
    """text mode 결과(cohort_results_summary.json)와 browser 결과 자동 매칭."""
    summary_path = _BASE / "experiments" / "outbound" / "cohort_results_summary.json"
    if not summary_path.exists():
        print(f"❌ {summary_path} 없음")
        return

    with open(summary_path) as f:
        summary = json.load(f)

    out_dir = _BASE / "experiments" / "text_vs_browser"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_comparisons = {}

    for target in summary["targets"]:
        slug = target["slug"]
        text_result_path = target["result_path"]

        # browser 결과 찾기 (cohort_results/cohort_manual5_*.json)
        browser_results = sorted((_BASE / "cohort_results").glob("cohort_manual5_*.json"))
        if not browser_results:
            print(f"⚠️ {slug}: browser 결과 없음, 스킵")
            continue

        # 최신 browser 결과 사용 — 사이트별 매칭은 사용자가 직접 지정
        # 여기선 일단 가장 최신 것
        browser_path = browser_results[-1]
        try:
            text_result = load_result(text_result_path)
            browser_result = load_result(browser_path)
        except FileNotFoundError as e:
            print(f"⚠️ {slug}: 파일 못 찾음 {e}")
            continue

        # browser_result의 url과 target url 비교
        if browser_result.get("url") != target["url"]:
            continue

        comparison = compare_pair(text_result, browser_result)
        all_comparisons[slug] = comparison
        print(f"\n=== {target['company']} ({slug}) ===")
        print(f"  Text:    n={comparison['text_aggregate']['n']}, turns_avg={comparison['text_aggregate']['turns_avg']}, prob={comparison['text_aggregate']['conv_prob_mean']}")
        print(f"  Browser: n={comparison['browser_aggregate']['n']}, turns_avg={comparison['browser_aggregate']['turns_avg']}, prob={comparison['browser_aggregate']['conv_prob_mean']}")
        print(f"  Consistency: {comparison['overall_consistency_score']:.3f} — {comparison['interpretation']}")

    # 저장
    out_path = out_dir / "comparison_summary.json"
    with open(out_path, "w") as f:
        json.dump(all_comparisons, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {out_path}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        auto_compare()
        return

    if len(sys.argv) < 4:
        print("Usage: python compare.py <site_slug> <text_result.json> <browser_result.json>")
        print("       python compare.py --auto")
        sys.exit(1)

    slug, text_path, browser_path = sys.argv[1], sys.argv[2], sys.argv[3]
    text_result = load_result(text_path)
    browser_result = load_result(browser_path)
    comparison = compare_pair(text_result, browser_result)
    print(json.dumps({slug: comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
