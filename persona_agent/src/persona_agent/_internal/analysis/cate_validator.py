"""CATE Validator — 41R 예측 vs 실제 A/B 결과의 통계적 일치 검증.

H2 진입 시 핵심 모듈:
  - 41R는 "세그먼트 X에서 분기가 일어날 것"이라고 예측 (cohort 시뮬)
  - 고객이 실제 A/B 돌리고 결과 (사용자별 outcome + segment label) 제공
  - 이 모듈은 EconML로 Heterogeneous Treatment Effect(CATE)를 추정 →
    41R 예측한 분기 세그먼트와 실제 CATE split이 일치하는지 검증

학술 근거:
  - Chernozhukov et al., Econometrica 2025, Generic ML Inference on HTE
  - py-why/EconML v0.16.0 (DML, X-Learner, CausalForest)

작동 모드:
  1. EconML 있으면 → CausalForestDML 사용
  2. 없으면 → segment-level naïve CATE (그룹별 평균 차이 + bootstrap)

양쪽 모두 41R 예측과 비교한 일치도(matching score) 출력.

사용:
    from persona_agent.analysis import validate_predictions
    result = validate_predictions(
        ab_data=[
            {"user_id": "u1", "variant": "A", "outcome": 1, "segment": "impulsive"},
            ...
        ],
        prediction_41r={
            "diverging_segments": ["impulsive", "budget"],
            "predicted_winners": {"impulsive": "B", "cautious": "A", "budget": "B"},
        },
    )
"""

from __future__ import annotations

import json
import logging
import math
import random
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── EconML lazy import ──
def _try_econml():
    try:
        from econml.dml import CausalForestDML
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
        return CausalForestDML, RandomForestRegressor, RandomForestClassifier
    except ImportError:
        return None, None, None


@dataclass
class CATEResult:
    method: str  # "econml_causalforest" | "naive_segment_diff"
    segment_cates: dict[str, dict]  # {segment: {cate, ci_lower, ci_upper, n}}
    discovered_diverging_segments: list[str]
    overall_ate: float
    notes: list[str]


def _segment_naive_cate(ab_data: list[dict], n_bootstrap: int = 500, seed: int = 42) -> CATEResult:
    """EconML 없이 segment-level CATE 추정 (그룹별 평균 차이 + paired bootstrap).

    ab_data: [{user_id, variant ('A'/'B'), outcome (0/1), segment}]
    """
    by_segment = defaultdict(lambda: {"A": [], "B": []})
    for row in ab_data:
        seg = row.get("segment", "_unknown")
        var = row.get("variant")
        out = float(row.get("outcome", 0))
        if var in ("A", "B"):
            by_segment[seg][var].append(out)

    rng = random.Random(seed)
    segment_cates = {}

    # Overall ATE
    all_a = [o for seg_data in by_segment.values() for o in seg_data["A"]]
    all_b = [o for seg_data in by_segment.values() for o in seg_data["B"]]
    overall_ate = (sum(all_b) / len(all_b) - sum(all_a) / len(all_a)) if all_a and all_b else 0.0

    diverging = []

    for seg, data in by_segment.items():
        a, b = data["A"], data["B"]
        if not a or not b:
            continue
        cate = sum(b) / len(b) - sum(a) / len(a)

        # Bootstrap CI
        deltas = []
        for _ in range(n_bootstrap):
            sa = [rng.choice(a) for _ in range(len(a))]
            sb = [rng.choice(b) for _ in range(len(b))]
            deltas.append(sum(sb) / len(sb) - sum(sa) / len(sa))
        deltas.sort()
        ci_lower = deltas[int(0.025 * n_bootstrap)]
        ci_upper = deltas[int(0.975 * n_bootstrap)]

        segment_cates[seg] = {
            "cate": round(cate, 4),
            "ci95_lower": round(ci_lower, 4),
            "ci95_upper": round(ci_upper, 4),
            "n_a": len(a),
            "n_b": len(b),
            "diverges_from_overall": (
                (cate > 0 and overall_ate < 0) or (cate < 0 and overall_ate > 0)
                or abs(cate - overall_ate) > max(0.02, abs(overall_ate))
            ),
        }
        if segment_cates[seg]["diverges_from_overall"]:
            diverging.append(seg)

    return CATEResult(
        method="naive_segment_diff",
        segment_cates=segment_cates,
        discovered_diverging_segments=diverging,
        overall_ate=round(overall_ate, 4),
        notes=["EconML 미설치 — naive segment difference 사용. H2 정식 운영 시 econml 설치 권장."],
    )


def _econml_cate(ab_data: list[dict], features: list[str] | None = None) -> CATEResult:
    """EconML CausalForestDML로 정식 CATE 추정.

    features 없으면 segment를 one-hot encoding.
    """
    CausalForestDML, RFRegressor, RFClassifier = _try_econml()
    if CausalForestDML is None:
        raise RuntimeError("EconML 미설치")

    import numpy as np

    # 특성 행렬 구축
    segments = sorted({row.get("segment", "_unknown") for row in ab_data})
    seg_idx = {s: i for i, s in enumerate(segments)}

    X = np.zeros((len(ab_data), len(segments)))
    T = np.zeros(len(ab_data))
    Y = np.zeros(len(ab_data))
    for i, row in enumerate(ab_data):
        X[i, seg_idx[row.get("segment", "_unknown")]] = 1
        T[i] = 1 if row.get("variant") == "B" else 0
        Y[i] = float(row.get("outcome", 0))

    est = CausalForestDML(
        model_y=RFRegressor(n_estimators=50, random_state=42),
        model_t=RFClassifier(n_estimators=50, random_state=42),
        n_estimators=200,
        random_state=42,
        discrete_treatment=True,
    )
    est.fit(Y, T, X=X)

    segment_cates = {}
    diverging = []
    overall_ate = float(np.mean(est.effect(X)))

    for seg, idx in seg_idx.items():
        seg_X = np.zeros((1, len(segments)))
        seg_X[0, idx] = 1
        cate = float(est.effect(seg_X)[0])
        try:
            lower, upper = est.effect_interval(seg_X, alpha=0.05)
            ci_lower, ci_upper = float(lower[0]), float(upper[0])
        except Exception:
            ci_lower = ci_upper = float("nan")
        n_seg = int((X[:, idx] == 1).sum())
        diverges = abs(cate - overall_ate) > max(0.02, abs(overall_ate))
        segment_cates[seg] = {
            "cate": round(cate, 4),
            "ci95_lower": round(ci_lower, 4) if not math.isnan(ci_lower) else None,
            "ci95_upper": round(ci_upper, 4) if not math.isnan(ci_upper) else None,
            "n": n_seg,
            "diverges_from_overall": bool(diverges),
        }
        if diverges:
            diverging.append(seg)

    return CATEResult(
        method="econml_causalforest",
        segment_cates=segment_cates,
        discovered_diverging_segments=diverging,
        overall_ate=round(overall_ate, 4),
        notes=["EconML CausalForestDML — Chernozhukov et al. 2025 방법론."],
    )


def validate_predictions(
    ab_data: list[dict],
    prediction_41r: dict,
    prefer_econml: bool = True,
) -> dict:
    """41R 예측과 실제 A/B 결과를 비교, 일치도 점수 계산.

    prediction_41r:
      {
        "diverging_segments": ["impulsive", "budget"],
        "predicted_winners": {"impulsive": "B", ...},  # optional
      }

    Returns:
      {
        "cate_estimation": <CATEResult dict>,
        "agreement_score": float (0~1),
        "predicted_diverging": [...],
        "actual_diverging": [...],
        "true_positive": [...],
        "false_positive": [...],
        "false_negative": [...],
        "winner_agreement": {...},
      }
    """
    if prefer_econml:
        try:
            cate = _econml_cate(ab_data)
        except (RuntimeError, ImportError):
            cate = _segment_naive_cate(ab_data)
    else:
        cate = _segment_naive_cate(ab_data)

    predicted = set(prediction_41r.get("diverging_segments", []))
    actual = set(cate.discovered_diverging_segments)

    tp = predicted & actual
    fp = predicted - actual
    fn = actual - predicted

    # F1-like agreement
    if not predicted and not actual:
        agreement = 1.0
    elif not predicted or not actual:
        agreement = 0.0
    else:
        precision = len(tp) / len(predicted) if predicted else 0
        recall = len(tp) / len(actual) if actual else 0
        agreement = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

    # Winner agreement (예측한 segment에 한해서)
    winner_agree = {}
    for seg, predicted_winner in (prediction_41r.get("predicted_winners") or {}).items():
        if seg in cate.segment_cates:
            actual_cate = cate.segment_cates[seg]["cate"]
            actual_winner = "B" if actual_cate > 0 else "A"
            winner_agree[seg] = {
                "predicted": predicted_winner,
                "actual_winner": actual_winner,
                "actual_cate": actual_cate,
                "match": predicted_winner == actual_winner,
            }

    n_winner_match = sum(1 for v in winner_agree.values() if v["match"])
    winner_acc = n_winner_match / len(winner_agree) if winner_agree else None

    return {
        "cate_estimation": {
            "method": cate.method,
            "overall_ate": cate.overall_ate,
            "segment_cates": cate.segment_cates,
            "discovered_diverging_segments": cate.discovered_diverging_segments,
            "notes": cate.notes,
        },
        "predicted_diverging": sorted(predicted),
        "actual_diverging": sorted(actual),
        "true_positive": sorted(tp),
        "false_positive": sorted(fp),
        "false_negative": sorted(fn),
        "agreement_score": round(agreement, 3),
        "winner_agreement": winner_agree,
        "winner_accuracy": round(winner_acc, 3) if winner_acc is not None else None,
        "interpretation": (
            f"41R가 예측한 분기 세그먼트 {sorted(predicted)} vs 실제 CATE 분기 {sorted(actual)}: "
            f"F1={agreement:.2f}. "
            + (f"승자 예측 정확도 {winner_acc:.0%} ({n_winner_match}/{len(winner_agree)})." if winner_acc else "")
        ),
    }


def main():
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 3:
        print("Usage:")
        print("  .venv/bin/python3 -m modules.cate_validator <ab_data.json> <prediction_41r.json>")
        print("")
        print("ab_data.json: [{user_id, variant 'A'/'B', outcome 0/1, segment}, ...]")
        print("prediction_41r.json: {diverging_segments: [...], predicted_winners: {seg: 'A'|'B', ...}}")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        ab = json.load(f)
    with open(sys.argv[2]) as f:
        pred = json.load(f)

    result = validate_predictions(ab, pred)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
