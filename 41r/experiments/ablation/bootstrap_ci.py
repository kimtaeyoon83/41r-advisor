"""Bootstrap Confidence Interval for n=200 ablation results.

n=200 ablation은 paired McNemar로 p<0.001을 보였지만,
"+16%p divergence" 자체의 신뢰구간(uncertainty band)은 없다.
이 스크립트는 199회 resampling으로 +16%p의 95% CI를 계산한다.

CPO 질문 대비:
  Q: "16%p가 진짜인지 노이즈인지?"
  A: "95% CI는 [+X.X, +Y.Y]%p — 0을 포함하지 않으므로 진짜 효과"

참고: case 단위 paired bootstrap (같은 case에서 arm A/B 결과를 함께 샘플)
"""

from __future__ import annotations

import json
import logging
import random
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_RESULTS = _BASE / "results_ablation_n200.json"
_OUT = _BASE / "bootstrap_ci_n200.json"
_N_BOOTSTRAP = 1000  # 199 권고치 이상으로


def _percentile(values: list[float], p: float) -> float:
    """Linear interpolation percentile (numpy 없이)."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def paired_bootstrap(
    arm_a_results: list[dict],
    arm_b_results: list[dict],
    n_iter: int = _N_BOOTSTRAP,
    seed: int = 42,
) -> dict:
    """Paired bootstrap on case-level results.

    각 iteration마다 N개 case를 with-replacement로 샘플 → 두 arm의 metric 차이 계산.
    """
    rng = random.Random(seed)
    n = len(arm_a_results)
    assert n == len(arm_b_results), "arm A/B 케이스 수가 다름"

    # case_id로 인덱싱 (paired 보장)
    a_by_id = {r["case_id"]: r for r in arm_a_results}
    b_by_id = {r["case_id"]: r for r in arm_b_results}
    case_ids = list(a_by_id.keys())

    deltas_acc = []
    deltas_div = []

    for it in range(n_iter):
        sampled = [rng.choice(case_ids) for _ in range(n)]
        a_sample = [a_by_id[cid] for cid in sampled]
        b_sample = [b_by_id[cid] for cid in sampled]

        a_acc = sum(1 for r in a_sample if r["match"]) / n
        b_acc = sum(1 for r in b_sample if r["match"]) / n
        a_div = sum(1 for r in a_sample if r["segment_divergence"]) / n
        b_div = sum(1 for r in b_sample if r["segment_divergence"]) / n

        deltas_acc.append((b_acc - a_acc) * 100)
        deltas_div.append((b_div - a_div) * 100)

    return {
        "n_cases": n,
        "n_bootstrap": n_iter,
        "seed": seed,
        "delta_accuracy_pp": {
            "mean": round(sum(deltas_acc) / n_iter, 2),
            "ci95_lower": round(_percentile(deltas_acc, 0.025), 2),
            "ci95_upper": round(_percentile(deltas_acc, 0.975), 2),
            "ci90_lower": round(_percentile(deltas_acc, 0.05), 2),
            "ci90_upper": round(_percentile(deltas_acc, 0.95), 2),
            "includes_zero_in_95ci": _percentile(deltas_acc, 0.025) <= 0 <= _percentile(deltas_acc, 0.975),
        },
        "delta_divergence_pp": {
            "mean": round(sum(deltas_div) / n_iter, 2),
            "ci95_lower": round(_percentile(deltas_div, 0.025), 2),
            "ci95_upper": round(_percentile(deltas_div, 0.975), 2),
            "ci90_lower": round(_percentile(deltas_div, 0.05), 2),
            "ci90_upper": round(_percentile(deltas_div, 0.95), 2),
            "includes_zero_in_95ci": _percentile(deltas_div, 0.025) <= 0 <= _percentile(deltas_div, 0.975),
        },
    }


def main():
    if not _RESULTS.exists():
        logger.error("results 없음: %s — run_ablation_n200.py 먼저 실행", _RESULTS)
        sys.exit(1)

    with open(_RESULTS) as f:
        data = json.load(f)

    logger.info("Bootstrap CI: n=%d, iterations=%d", data["n"], _N_BOOTSTRAP)
    ci = paired_bootstrap(data["arm_a_results"], data["arm_b_results"])

    summary = {
        "source": str(_RESULTS),
        "dataset": data.get("dataset", "Upworthy"),
        "point_estimate": {
            "delta_accuracy_pp": data.get("delta_accuracy_pp"),
            "delta_divergence_pp": data.get("delta_divergence_pp"),
        },
        "bootstrap": ci,
        "interpretation": {
            "divergence": (
                f"분기 탐지 +{data.get('delta_divergence_pp', 0)}%p "
                f"(95% CI: [{ci['delta_divergence_pp']['ci95_lower']:+.2f}, {ci['delta_divergence_pp']['ci95_upper']:+.2f}]%p) — "
                + ("⚠️ CI가 0 포함 (효과 불확실)"
                   if ci["delta_divergence_pp"]["includes_zero_in_95ci"]
                   else "✅ CI가 0 미포함 (효과 통계적으로 실재)")
            ),
            "accuracy": (
                f"정확도 {data.get('delta_accuracy_pp', 0):+.1f}%p "
                f"(95% CI: [{ci['delta_accuracy_pp']['ci95_lower']:+.2f}, {ci['delta_accuracy_pp']['ci95_upper']:+.2f}]%p) — "
                + ("⚠️ CI가 0 포함 (Demo와 유의차 없음 — 우리 강점 아님)"
                   if ci["delta_accuracy_pp"]["includes_zero_in_95ci"]
                   else "✅ CI가 0 미포함 (실제 차이)")
            ),
        },
    }

    with open(_OUT, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("BOOTSTRAP CI (n=1000)")
    logger.info("=" * 60)
    logger.info(summary["interpretation"]["divergence"])
    logger.info(summary["interpretation"]["accuracy"])
    logger.info("Saved: %s", _OUT)
    return summary


if __name__ == "__main__":
    main()
