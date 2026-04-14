"""Ablation v4 — n=200 Upworthy 케이스로 통계 유의성 확보.

기존 v3 (n=12)와 동일 구조, cases.json만 Upworthy로 교체.

비용 추정: 200 × 2 arm × 5 페르소나 = 2000 LLM call ≈ $30
시간 추정: ThreadPool 5 동시, ~30분
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.cache import cache_disabled
from experiments.ablation.run_ablation import (
    PERSONAS_A, PERSONAS_B,
    evaluate_case, aggregate_prediction
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_CASES = _BASE.parent / "datasets" / "upworthy" / "ablation_cases_n200.json"
_OUT = _BASE / "results_ablation_n200.json"


def run_arm(arm_name, personas, cases):
    """한 arm 실행 (이미 셔플된 케이스 사용)."""
    arm_results = []
    correct = 0
    import concurrent.futures

    def _evaluate(idx_case):
        idx, case = idx_case
        evals = []
        for pid, persona in personas.items():
            ev = evaluate_case(case, pid, persona)
            evals.append(ev)
        predicted = aggregate_prediction(evals)
        actual = case["known_winner"]
        match = predicted == actual
        winners = set(e.get("predicted_winner") for e in evals if e.get("predicted_winner") in ("A", "B"))
        return idx, {
            "case_id": case["id"],
            "actual_winner": actual,
            "predicted_winner": predicted,
            "match": match,
            "segment_divergence": len(winners) > 1,
            "lift_pct": case.get("lift_pct"),
            "swapped": case.get("swapped"),
            "persona_evaluations": evals,
        }

    # 3 동시 (rate limit 안전)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_evaluate, (i, c)): i for i, c in enumerate(cases)}
        completed_results = [None] * len(cases)
        for future in concurrent.futures.as_completed(futures):
            try:
                idx, result = future.result(timeout=120)
                completed_results[idx] = result
                if result["match"]:
                    correct += 1
                if (idx + 1) % 20 == 0:
                    logger.info("[Arm %s] %d/%d completed, accuracy so far: %.1f%%",
                                arm_name, sum(1 for r in completed_results if r), len(cases),
                                correct / sum(1 for r in completed_results if r) * 100)
            except Exception as e:
                logger.exception("Case 실패: %s", e)

    arm_results = [r for r in completed_results if r is not None]
    accuracy = correct / len(arm_results) if arm_results else 0
    divergence = sum(1 for r in arm_results if r["segment_divergence"])

    return {
        "arm": arm_name,
        "accuracy_pct": round(accuracy * 100, 1),
        "correct": correct,
        "total": len(arm_results),
        "divergence_count": divergence,
        "divergence_pct": round(divergence / len(arm_results) * 100, 1),
        "results": arm_results,
    }


def run():
    with open(_CASES) as f:
        cases = json.load(f)
    logger.info("Loaded %d cases (Upworthy)", len(cases))

    logger.info("=" * 70)
    logger.info("ARM A: Demo-only (n=%d)", len(cases))
    logger.info("=" * 70)
    arm_a = run_arm("A", PERSONAS_A, cases)

    logger.info("=" * 70)
    logger.info("ARM B: Demo + Persona (41R) (n=%d)", len(cases))
    logger.info("=" * 70)
    arm_b = run_arm("B", PERSONAS_B, cases)

    summary = {
        "n": len(cases),
        "dataset": "Upworthy Research Archive (exploratory)",
        "arm_a": {
            "accuracy_pct": arm_a["accuracy_pct"],
            "correct": arm_a["correct"],
            "divergence_pct": arm_a["divergence_pct"],
        },
        "arm_b": {
            "accuracy_pct": arm_b["accuracy_pct"],
            "correct": arm_b["correct"],
            "divergence_pct": arm_b["divergence_pct"],
        },
        "delta_accuracy_pp": round(arm_b["accuracy_pct"] - arm_a["accuracy_pct"], 1),
        "delta_divergence_pp": round(arm_b["divergence_pct"] - arm_a["divergence_pct"], 1),
        "arm_a_results": arm_a["results"],
        "arm_b_results": arm_b["results"],
    }

    with open(_OUT, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("RESULTS (n=%d)", len(cases))
    logger.info("Arm A (Demo-only):  %.1f%% accuracy | %.1f%% divergence",
                arm_a["accuracy_pct"], arm_a["divergence_pct"])
    logger.info("Arm B (41R):        %.1f%% accuracy | %.1f%% divergence",
                arm_b["accuracy_pct"], arm_b["divergence_pct"])
    logger.info("Delta:              %+.1f%%p accuracy | %+.1f%%p divergence",
                summary["delta_accuracy_pp"], summary["delta_divergence_pp"])
    logger.info("Saved: %s", _OUT)
    return summary


if __name__ == "__main__":
    with cache_disabled():
        run()
