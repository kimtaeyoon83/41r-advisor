"""CATE Validator Self-Demo — n=200 ablation 데이터를 합성 A/B로 변환 → 검증.

목적:
  F2 NDA 파트너 미팅 시 "이렇게 검증합니다" 시연 자료.
  실제 고객 데이터 없어도 자체 데이터로 cate_validator 워크플로우 시연.

변환 규칙:
  - segment = persona_id (5개 demographic; arm A/B가 다른 ID 쓰므로 위치 기반 매핑)
  - variant = 'A' (Demo-only arm) or 'B' (41R arm) — 41R 자체가 처치(treatment)
  - outcome = 1 if predicted_winner == actual_winner else 0 (정확도)
  - 41R 예측: "어느 segment에서 41R가 Demo보다 효과적인가" (CATE > 0)

CATE 해석:
  - segment_cates[seg]['cate'] > 0: 그 페르소나에게 41R가 Demo보다 더 잘 맞춤
  - cate < 0: 41R가 오히려 손해
  - diverges_from_overall: 평균 효과와 다른 페르소나 (이질성 신호)

사용:
    .venv/bin/python3 experiments/cate_self_demo/run_self_demo.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modules.cate_validator import validate_predictions

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_ABLATION = _BASE.parent / "ablation" / "results_ablation_n200.json"
_OUT_JSON = _BASE / "result.json"
_OUT_MD = _BASE / "SUMMARY.md"

# arm_a (Demo-only)와 arm_b (41R)는 서로 다른 persona_id 사용
# 위치 기반 매핑 (둘 다 같은 순서: 충동/신중/가격민감/실용/시니어)
PERSONA_MAP = {
    "demo_young_m": "20대 남성 (직장인)",
    "p_impulsive": "20대 남성 (직장인)",
    "demo_adult_f": "30대 여성 (회계)",
    "p_cautious": "30대 여성 (회계)",
    "demo_adult_f2": "30대 여성 (교사)",
    "p_budget": "30대 여성 (교사)",
    "demo_adult_m": "40대 남성 (IT)",
    "p_pragmatic": "40대 남성 (IT)",
    "demo_senior_f": "50대+ 여성",
    "p_senior": "50대+ 여성",
}


def convert_to_ab_data(ablation: dict) -> list[dict]:
    """ablation results → cate_validator가 받는 A/B 형식.

    각 (case, persona, arm) 조합 → 한 row.
    """
    rows = []
    for arm_label, results_key in [("A", "arm_a_results"), ("B", "arm_b_results")]:
        for case in ablation.get(results_key, []):
            actual = case.get("actual_winner")
            for ev in case.get("persona_evaluations", []):
                pid = ev.get("persona_id")
                seg = PERSONA_MAP.get(pid, pid)
                predicted = ev.get("predicted_winner")
                outcome = 1 if predicted == actual else 0
                rows.append({
                    "user_id": f"{case['case_id']}_{pid}_{arm_label}",
                    "variant": arm_label,
                    "outcome": outcome,
                    "segment": seg,
                })
    return rows


def main():
    if not _ABLATION.exists():
        logger.error("ablation 데이터 없음: %s", _ABLATION)
        sys.exit(1)

    with open(_ABLATION) as f:
        ablation = json.load(f)

    ab_data = convert_to_ab_data(ablation)
    logger.info("변환 완료: %d rows (case×persona×arm)", len(ab_data))

    # 41R "예측": divergence 일으킬 segment가 어디인가 (가설)
    # 사전에 정해진 가설 — 본 데모에서는 "전 segment에 효과 있을 것"으로 기본 설정
    prediction_41r = {
        "diverging_segments": list(set(PERSONA_MAP.values())),
        "predicted_winners": {seg: "B" for seg in set(PERSONA_MAP.values())},  # 41R가 더 잘 맞출 것
    }

    result = validate_predictions(ab_data, prediction_41r, prefer_econml=True)

    # 결과 보강 (해석)
    interpretation = []
    for seg, info in result["cate_estimation"]["segment_cates"].items():
        cate = info["cate"]
        ci_lo = info.get("ci95_lower", 0)
        ci_hi = info.get("ci95_upper", 0)
        ci_includes_zero = (ci_lo is not None and ci_hi is not None
                            and ci_lo <= 0 <= ci_hi)
        if cate > 0.05 and not ci_includes_zero:
            verdict = f"✅ 41R 우위 +{cate*100:.1f}%p (CI 0 미포함)"
        elif cate < -0.05 and not ci_includes_zero:
            verdict = f"❌ 41R 손해 {cate*100:.1f}%p (CI 0 미포함)"
        elif ci_includes_zero:
            verdict = f"⚪ 효과 불확실 (CI 0 포함, CATE={cate*100:+.1f}%p)"
        else:
            verdict = f"⚪ 효과 미미 (CATE={cate*100:+.1f}%p)"
        interpretation.append(f"- **{seg}**: {verdict}")

    summary = {
        "demo_version": "cate_self_demo_v1",
        "source": str(_ABLATION),
        "n_rows_converted": len(ab_data),
        "n_segments": len(set(PERSONA_MAP.values())),
        "ate_41r_vs_demo": result["cate_estimation"]["overall_ate"],
        "result": result,
        "per_segment_verdict": interpretation,
        "use_in_outbound": (
            "F2 NDA 파트너 미팅 시 시연: '같은 방법론으로 귀사 A/B 데이터를 분석합니다'"
        ),
    }

    with open(_OUT_JSON, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # SUMMARY.md
    md = [
        "# CATE Validator Self-Demo — n=200 Ablation 데이터 활용",
        "",
        "## 목적",
        "F2 NDA 파트너에게 \"실제 A/B 데이터로 어떻게 41R 예측을 검증하는지\" 시연.",
        "",
        "## 변환",
        f"- Source: `{_ABLATION.name}` (n=200 Upworthy ablation)",
        f"- Rows: **{len(ab_data)}** (200 cases × 5 personas × 2 arms)",
        f"- Segment: {len(set(PERSONA_MAP.values()))}개 인구통계 segment",
        "- Variant: A=Demo-only arm, B=41R arm",
        "- Outcome: A/B winner 예측 적중 = 1, 빗나감 = 0",
        "",
        f"## CATE 추정 방법: `{result['cate_estimation']['method']}`",
        result['cate_estimation']['notes'][0] if result['cate_estimation']['notes'] else "",
        "",
        f"## Overall ATE (41R - Demo): **{result['cate_estimation']['overall_ate']*100:+.1f}%p**",
        "",
        "## Per-Segment 결과",
        "",
        *interpretation,
        "",
        "## 41R 예측 vs 실제 일치도",
        f"- 예측한 분기 segment: {result['predicted_diverging']}",
        f"- 실제 분기 segment: {result['actual_diverging']}",
        f"- True Positive: {result['true_positive']}",
        f"- False Positive: {result['false_positive']}",
        f"- False Negative: {result['false_negative']}",
        f"- **F1 일치도: {result['agreement_score']:.2f}**",
        "",
        "## 활용",
        "1. **F2 NDA 파트너 미팅 시연자료**: \"귀사 A/B 데이터에 같은 검증 적용\"",
        "2. **자체 데이터로 워크플로우 검증됨** = 외부 데이터 0건이어도 방법론 검증 가능",
        "3. **경쟁사 비교**: Aaru, UXAgent, Maze 모두 CATE validator 미보유",
        "",
        "## 한계",
        "- 본 데모는 self-data (Upworthy A/B 헤드라인) — 실제 e-commerce/SaaS 데이터 아님",
        "- segment 정의가 인구통계 5종에 국한 — 실제 고객은 다른 segment 정의 가능",
        "- 41R의 \"diverging_segments\" 사전 예측은 본 데모에서 가설적 (모든 segment)",
        "",
        "## Reproduction",
        "```bash",
        ".venv/bin/python3 experiments/cate_self_demo/run_self_demo.py",
        "```",
    ]

    _OUT_MD.write_text("\n".join(md), encoding="utf-8")

    logger.info("=" * 60)
    logger.info("CATE Self-Demo 완료")
    logger.info("=" * 60)
    logger.info("Method: %s", result['cate_estimation']['method'])
    logger.info("Overall ATE: %+.1f%%p", result['cate_estimation']['overall_ate'] * 100)
    logger.info("F1 agreement: %.2f", result['agreement_score'])
    logger.info("Saved: %s", _OUT_JSON)
    logger.info("Saved: %s", _OUT_MD)


if __name__ == "__main__":
    main()
