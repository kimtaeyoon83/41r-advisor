"""A/B 역검증 — 공개 A/B 테스트 케이스에 대한 페르소나 예측 정확도 측정.

사용법:
    ANTHROPIC_API_KEY=... python3 experiments/ab_validation/run_validation.py
"""

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.provider_router import call as llm_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_CASES_PATH = _BASE / "cases.json"
_RESULTS_PATH = _BASE / "results.json"

# 페르소나 요약 (soul에서 핵심만 추출)
PERSONAS = {
    "p_impulsive": {
        "name": "충동형 민수 (28세, 스타트업 마케터)",
        "profile": """
- 인내심: 2초 (로딩 3초 넘으면 이탈)
- 결정 속도: 0.5초
- 시각 의존도: 0.9 (시각적 CTA에 즉시 반응)
- 리서치 깊이: 0.1 (거의 안 읽음)
- 프라이버시 민감도: 0.2 (신경 안 씀)
- 가격 민감도: 0.3 (가격보다 편의성)
- 소셜프루프 가중치: 0.7
- 신뢰 중요: 별점, 구매후기 사진, 할인배너
- 신뢰 무관: 회사연혁, 인증서, 개인정보정책
- 좌절 트리거: 느린 로딩, 팝업, 강제 회원가입, 스크롤 3회 이상
""",
    },
    "p_cautious": {
        "name": "신중형 지영 (35세, 회계법인 시니어)",
        "profile": """
- 인내심: 10초
- 결정 속도: 3초 (꼼꼼히 비교)
- 시각 의존도: 0.3 (텍스트 위주)
- 리서치 깊이: 0.95 (모든 정보 확인)
- 프라이버시 민감도: 0.8 (매우 민감)
- 가격 민감도: 0.6 (가성비 중시)
- 소셜프루프 가중치: 0.5
- 신뢰 중요: 회사연혁 5년+, 고객사례 3개+, 환불정책, 리뷰 100개+
- 신뢰 무관: 할인배너, 한정수량, 타이머
- 좌절 트리거: 가격숨김, 환불정책 불명확, 리뷰 부족, 회사정보 없음
""",
    },
}

EVALUATION_SYSTEM = """당신은 UX 행동 예측 전문가입니다.

A/B 테스트의 두 variant 설명을 보고, 주어진 페르소나가 어느 variant에서 더 높은 확률로 전환(가입, 구매, 클릭 등)할지 예측합니다.

## 규칙
1. 페르소나의 성향 프로필(인내심, 결정속도, 시각의존도, 리서치깊이 등)에 근거하여 판단
2. 추측이 아닌 페르소나 특성과 variant 특성의 매칭으로 결론 도출
3. 확신도를 1~5로 표시 (1=거의 모르겠음, 5=확실)

## 출력 형식 (JSON만, 다른 텍스트 없이)
```json
{
  "predicted_winner": "A" 또는 "B",
  "confidence": 1~5,
  "reasoning": "이 페르소나가 왜 이 variant를 선호하는지 2~3문장",
  "persona_behavior_a": "이 페르소나가 variant A에서 보일 행동 1문장",
  "persona_behavior_b": "이 페르소나가 variant B에서 보일 행동 1문장"
}
```"""


def evaluate_case(case: dict, persona_id: str, persona: dict) -> dict:
    """한 케이스를 한 페르소나로 평가."""
    user_msg = f"""## 페르소나: {persona["name"]}
{persona["profile"]}

## A/B 테스트: {case["company"]} — {case["test_description"]}

**Variant A**: {case["variant_a"]}

**Variant B**: {case["variant_b"]}

이 페르소나는 어느 variant에서 더 높은 확률로 전환할까요?"""

    response = llm_call(
        "review_proposer",  # MID tier (Sonnet)
        [{"role": "user", "content": user_msg}],
        system=EVALUATION_SYSTEM,
        max_tokens=1024,
    )

    raw = response.get("content", "")
    try:
        # JSON 추출
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(raw[start:end])
        else:
            result = {"predicted_winner": "?", "confidence": 0, "reasoning": raw}
    except json.JSONDecodeError:
        result = {"predicted_winner": "?", "confidence": 0, "reasoning": raw}

    result["persona_id"] = persona_id
    result["case_id"] = case["id"]
    result["tokens"] = response.get("usage", {})
    return result


def aggregate_prediction(evals: list[dict]) -> str:
    """페르소나별 평가를 종합하여 최종 승자 예측."""
    votes = {"A": 0, "B": 0}
    for ev in evals:
        winner = ev.get("predicted_winner", "?")
        conf = ev.get("confidence", 1)
        if winner in votes:
            votes[winner] += conf  # 확신도 가중 투표
    return "A" if votes["A"] > votes["B"] else "B"


def run():
    with open(_CASES_PATH) as f:
        cases = json.load(f)

    all_results = []
    correct = 0
    total = len(cases)

    for i, case in enumerate(cases):
        logger.info("=== [%d/%d] %s — %s ===", i + 1, total, case["company"], case["test_description"])

        evals = []
        for pid, persona in PERSONAS.items():
            ev = evaluate_case(case, pid, persona)
            logger.info("  %s → predicted %s (conf %s)", pid, ev.get("predicted_winner"), ev.get("confidence"))
            evals.append(ev)

        predicted = aggregate_prediction(evals)
        actual = case["known_winner"]
        match = predicted == actual

        if match:
            correct += 1
            logger.info("  ✓ CORRECT — predicted %s, actual %s (lift %s%%)", predicted, actual, case["lift_pct"])
        else:
            logger.info("  ✗ WRONG — predicted %s, actual %s (lift %s%%)", predicted, actual, case["lift_pct"])

        all_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "test_description": case["test_description"],
            "known_winner": actual,
            "lift_pct": case["lift_pct"],
            "predicted_winner": predicted,
            "match": match,
            "persona_evaluations": evals,
        })

    accuracy = correct / total if total > 0 else 0

    summary = {
        "total_cases": total,
        "correct": correct,
        "accuracy": round(accuracy * 100, 1),
        "results": all_results,
    }

    with open(_RESULTS_PATH, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("ACCURACY: %d/%d = %.1f%%", correct, total, accuracy * 100)
    logger.info("Results saved to %s", _RESULTS_PATH)

    return summary


if __name__ == "__main__":
    run()
