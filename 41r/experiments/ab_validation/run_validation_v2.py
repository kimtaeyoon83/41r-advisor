"""A/B 역검증 v2 — 라벨 셔플로 데이터 오염 통제.

v1에서 12/12 = 100% 나왔으나, 전부 B가 승자 + 학습 데이터 오염 의심.
v2: 절반의 케이스에서 A/B 라벨을 뒤집어서 테스트.

사용법:
    ANTHROPIC_API_KEY=... python3 experiments/ab_validation/run_validation_v2.py
"""

import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.provider_router import call as llm_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_CASES_PATH = _BASE / "cases.json"
_RESULTS_PATH = _BASE / "results_v2.json"

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
4. 회사 이름이나 유명 사례에 대한 사전 지식을 사용하지 마세요. 오직 variant 설명과 페르소나 프로필만으로 판단하세요.

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


def shuffle_case(case: dict, swap: bool) -> tuple[dict, str]:
    """케이스의 A/B 라벨을 swap. 실제 승자 라벨도 반전."""
    if not swap:
        return case, case["known_winner"]

    shuffled = dict(case)
    shuffled["variant_a"] = case["variant_b"]
    shuffled["variant_b"] = case["variant_a"]
    # 승자도 반전
    actual = "A" if case["known_winner"] == "B" else "B"
    return shuffled, actual


def evaluate_case(case: dict, persona_id: str, persona: dict) -> dict:
    """한 케이스를 한 페르소나로 평가. 회사명을 익명화."""
    # 회사명을 제거하여 학습 데이터 오염 최소화
    user_msg = f"""## 페르소나: {persona["name"]}
{persona["profile"]}

## A/B 테스트: {case["test_description"]}

**Variant A**: {case["variant_a"]}

**Variant B**: {case["variant_b"]}

이 페르소나는 어느 variant에서 더 높은 확률로 전환할까요?
주의: 유명한 A/B 테스트 사례에 대한 사전 지식을 사용하지 마세요. 오직 위 설명과 페르소나 프로필만으로 판단하세요."""

    response = llm_call(
        "review_proposer",
        [{"role": "user", "content": user_msg}],
        system=EVALUATION_SYSTEM,
        max_tokens=1024,
    )

    raw = response.get("content", "")
    try:
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
    votes = {"A": 0, "B": 0}
    for ev in evals:
        winner = ev.get("predicted_winner", "?")
        conf = ev.get("confidence", 1)
        if winner in votes:
            votes[winner] += conf
    return "A" if votes["A"] > votes["B"] else "B"


def run():
    with open(_CASES_PATH) as f:
        cases = json.load(f)

    # 랜덤 시드 고정으로 재현 가능
    random.seed(42)
    # 절반의 케이스에서 A/B 라벨 swap
    swap_flags = [random.choice([True, False]) for _ in cases]

    logger.info("Swap flags: %s", swap_flags)
    logger.info("Swapped cases: %s", [c["id"] for c, s in zip(cases, swap_flags) if s])

    all_results = []
    correct = 0
    total = len(cases)

    for i, (case, swap) in enumerate(zip(cases, swap_flags)):
        shuffled, actual_winner = shuffle_case(case, swap)

        logger.info(
            "=== [%d/%d] %s (swapped=%s, actual_winner=%s) ===",
            i + 1, total, case["id"], swap, actual_winner
        )

        evals = []
        for pid, persona in PERSONAS.items():
            ev = evaluate_case(shuffled, pid, persona)
            logger.info("  %s → predicted %s (conf %s)", pid, ev.get("predicted_winner"), ev.get("confidence"))
            evals.append(ev)

        predicted = aggregate_prediction(evals)
        match = predicted == actual_winner

        if match:
            correct += 1
            logger.info("  ✓ CORRECT — predicted %s, actual %s", predicted, actual_winner)
        else:
            logger.info("  ✗ WRONG — predicted %s, actual %s", predicted, actual_winner)

        all_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "test_description": case["test_description"],
            "swapped": swap,
            "known_winner_original": case["known_winner"],
            "actual_winner_in_test": actual_winner,
            "lift_pct": case["lift_pct"],
            "predicted_winner": predicted,
            "match": match,
            "persona_evaluations": evals,
        })

    accuracy = correct / total if total > 0 else 0

    # 세부 분석
    swapped_cases = [r for r in all_results if r["swapped"]]
    unswapped_cases = [r for r in all_results if not r["swapped"]]
    swapped_correct = sum(1 for r in swapped_cases if r["match"])
    unswapped_correct = sum(1 for r in unswapped_cases if r["match"])

    summary = {
        "total_cases": total,
        "correct": correct,
        "accuracy_pct": round(accuracy * 100, 1),
        "swapped_count": len(swapped_cases),
        "swapped_correct": swapped_correct,
        "swapped_accuracy_pct": round(swapped_correct / len(swapped_cases) * 100, 1) if swapped_cases else 0,
        "unswapped_count": len(unswapped_cases),
        "unswapped_correct": unswapped_correct,
        "unswapped_accuracy_pct": round(unswapped_correct / len(unswapped_cases) * 100, 1) if unswapped_cases else 0,
        "results": all_results,
    }

    with open(_RESULTS_PATH, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("OVERALL: %d/%d = %.1f%%", correct, total, accuracy * 100)
    logger.info("UNSWAPPED (B=winner): %d/%d = %.1f%%", unswapped_correct, len(unswapped_cases),
                unswapped_correct / len(unswapped_cases) * 100 if unswapped_cases else 0)
    logger.info("SWAPPED (A=winner): %d/%d = %.1f%%", swapped_correct, len(swapped_cases),
                swapped_correct / len(swapped_cases) * 100 if swapped_cases else 0)
    logger.info("Results saved to %s", _RESULTS_PATH)

    return summary


if __name__ == "__main__":
    run()
