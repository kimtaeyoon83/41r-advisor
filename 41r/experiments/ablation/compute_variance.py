"""메트릭 4: 코호트 내 행동 variance.

두 가지 관점:
1. 예측 분포 엔트로피 — A/B 투표의 불확실성
2. 이유 텍스트 다양성 — 각 페르소나가 서로 다른 관점을 내는지
"""

import json
import math
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent
_RESULTS = _BASE / "results_ablation.json"
_OUT = _BASE / "metric_4_variance.json"


def entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    probs = [c / total for c in counts if c > 0]
    return -sum(p * math.log2(p) for p in probs)


def text_diversity(texts: list[str]) -> float:
    """이유 텍스트의 토큰 셋 Jaccard 거리 평균.

    다양할수록 높음 (0=동일, 1=완전 다름).
    """
    tokens_list = [set(t.split()) for t in texts if t]
    if len(tokens_list) < 2:
        return 0.0

    distances = []
    for i in range(len(tokens_list)):
        for j in range(i + 1, len(tokens_list)):
            a, b = tokens_list[i], tokens_list[j]
            if not a or not b:
                continue
            union = a | b
            inter = a & b
            jaccard_sim = len(inter) / len(union) if union else 0
            distances.append(1 - jaccard_sim)

    return sum(distances) / len(distances) if distances else 0.0


def compute_variance(arm_results: list[dict]) -> dict:
    """한 arm의 평균 variance."""
    entropies = []
    diversities = []

    for case in arm_results:
        evals = case["persona_evaluations"]

        # 예측 분포 엔트로피
        a_count = sum(1 for e in evals if e.get("predicted_winner") == "A")
        b_count = sum(1 for e in evals if e.get("predicted_winner") == "B")
        ent = entropy([a_count, b_count])
        entropies.append(ent)

        # 이유 텍스트 다양성
        reasons = [e.get("reasoning", "") for e in evals]
        div = text_diversity(reasons)
        diversities.append(div)

    return {
        "avg_prediction_entropy": round(sum(entropies) / len(entropies), 3) if entropies else 0,
        "avg_reasoning_diversity": round(sum(diversities) / len(diversities), 3) if diversities else 0,
        "case_entropies": [round(e, 3) for e in entropies],
        "case_diversities": [round(d, 3) for d in diversities],
    }


def main():
    with open(_RESULTS) as f:
        data = json.load(f)

    arm_a_var = compute_variance(data["arm_a_results"])
    arm_b_var = compute_variance(data["arm_b_results"])

    summary = {
        "metric": "behavioral_variance",
        "description": {
            "prediction_entropy": "0=전원동의, 1=극단분기 (Shannon entropy of A/B votes)",
            "reasoning_diversity": "0=동일한 이유, 1=완전 다른 이유 (avg Jaccard distance)",
        },
        "arm_a_demo_only": arm_a_var,
        "arm_b_41r": arm_b_var,
        "delta_entropy": round(arm_b_var["avg_prediction_entropy"] - arm_a_var["avg_prediction_entropy"], 3),
        "delta_diversity": round(arm_b_var["avg_reasoning_diversity"] - arm_a_var["avg_reasoning_diversity"], 3),
    }

    with open(_OUT, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("METRIC 4: Behavioral Variance")
    print("=" * 70)
    print(f"Arm A (Demo-only):")
    print(f"  Prediction entropy: {arm_a_var['avg_prediction_entropy']}")
    print(f"  Reasoning diversity: {arm_a_var['avg_reasoning_diversity']}")
    print()
    print(f"Arm B (41R):")
    print(f"  Prediction entropy: {arm_b_var['avg_prediction_entropy']}")
    print(f"  Reasoning diversity: {arm_b_var['avg_reasoning_diversity']}")
    print()
    print(f"Delta (B - A):")
    print(f"  Entropy: {summary['delta_entropy']:+.3f}")
    print(f"  Diversity: {summary['delta_diversity']:+.3f}")
    print(f"\nSaved: {_OUT}")


if __name__ == "__main__":
    main()
