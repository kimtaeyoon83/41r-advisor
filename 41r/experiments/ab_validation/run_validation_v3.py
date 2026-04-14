"""A/B 역검증 v3 — 5 페르소나 + 라벨 셔플.

v2 결과: 2 페르소나 66.7% (동점 시 집계 오류)
v3: 5 페르소나 (홀수)로 동점 제거 + 다양한 세그먼트 커버.

사용법:
    ANTHROPIC_API_KEY=... python3 experiments/ab_validation/run_validation_v3.py
"""

import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.cache import cache_disabled
from core.provider_router import call as llm_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
_CASES_PATH = _BASE / "cases.json"
_RESULTS_PATH = _BASE / "results_v3.json"

PERSONAS = {
    "p_impulsive": {
        "name": "충동형 민수 (28세, 스타트업 마케터)",
        "profile": """- 인내심: 2초, 결정속도: 0.5초, 시각의존: 0.9, 리서치: 0.1
- 가격민감도: 0.3, 프라이버시: 0.2, 소셜프루프: 0.7
- 신뢰: 별점, 후기사진, 할인배너 / 무시: 회사연혁, 인증서
- 좌절: 느린로딩, 팝업, 강제가입, 스크롤3회+""",
    },
    "p_cautious": {
        "name": "신중형 지영 (35세, 회계법인 시니어)",
        "profile": """- 인내심: 10초, 결정속도: 3초, 시각의존: 0.3, 리서치: 0.95
- 가격민감도: 0.6, 프라이버시: 0.8, 소셜프루프: 0.5
- 신뢰: 회사연혁5년+, 고객사례3+, 환불정책, 리뷰100+ / 무시: 할인배너, 한정수량, 타이머
- 좌절: 가격숨김, 환불불명확, 리뷰부족, 회사정보없음""",
    },
    "p_budget": {
        "name": "가격민감형 현주 (32세, 교사)",
        "profile": """- 인내심: 5초, 결정속도: 2초, 시각의존: 0.5, 리서치: 0.7
- 가격민감도: 0.95, 프라이버시: 0.5, 소셜프루프: 0.6
- 신뢰: 가격투명성, 환불보장, 무료체험, 할인코드 / 무시: 브랜드스토리, 디자인어워드
- 좌절: 가격안보임, 숨은수수료, 자동결제, 불투명할인, 비교불가요금제""",
    },
    "p_pragmatic": {
        "name": "실용주의형 준혁 (42세, IT팀장)",
        "profile": """- 인내심: 6초, 결정속도: 1.5초, 시각의존: 0.5, 리서치: 0.6
- 가격민감도: 0.5, 프라이버시: 0.4, 소셜프루프: 0.4
- 신뢰: 구체적수치, 고객사로고, 기술스펙, API문서 / 무시: 감성카피, 예쁜일러스트
- 좌절: 과장마케팅, 기능숨김, 비교표없음, 불필요단계""",
    },
    "p_senior": {
        "name": "시니어 영숙 (58세, 공무원)",
        "profile": """- 인내심: 15초, 결정속도: 5초, 시각의존: 0.7, 리서치: 0.5
- 가격민감도: 0.7, 프라이버시: 0.7, 소셜프루프: 0.8, 브랜드충성: 0.9
- 신뢰: 전화번호, 오래된회사, 지인추천, TV브랜드 / 무시: 트렌디디자인, SNS팔로워
- 좌절: 작은글씨, 클릭위치불명, 영어많음, 팝업, 뒤로가기초기화
- 테크문해력: 0.3, 단순한페이지선호, 큰버튼선호""",
    },
}

EVALUATION_SYSTEM = """당신은 UX 행동 예측 전문가입니다.

A/B 테스트의 두 variant 설명을 보고, 주어진 페르소나가 어느 variant에서 더 높은 확률로 전환(가입, 구매, 클릭 등)할지 예측합니다.

## 규칙
1. 페르소나의 성향 프로필에 근거하여 판단
2. 유명 A/B 테스트 사례에 대한 사전 지식을 사용하지 마세요. 오직 variant 설명과 페르소나 프로필만으로 판단
3. 확신도를 1~5로 표시

## 출력 (JSON만)
{"predicted_winner": "A" 또는 "B", "confidence": 1~5, "reasoning": "2~3문장"}"""


def shuffle_case(case, swap):
    if not swap:
        return case, case["known_winner"]
    shuffled = dict(case)
    shuffled["variant_a"] = case["variant_b"]
    shuffled["variant_b"] = case["variant_a"]
    actual = "A" if case["known_winner"] == "B" else "B"
    return shuffled, actual


def evaluate_case(case, persona_id, persona):
    user_msg = f"""## 페르소나: {persona["name"]}
{persona["profile"]}

## A/B 테스트: {case["test_description"]}
**Variant A**: {case["variant_a"]}
**Variant B**: {case["variant_b"]}

이 페르소나는 어느 variant에서 더 높은 확률로 전환할까요?"""

    response = llm_call(
        "review_proposer",
        [{"role": "user", "content": user_msg}],
        system=EVALUATION_SYSTEM,
        max_tokens=512,
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
    return result


def aggregate_prediction(evals):
    """가중 다수결. 5명이라 동점 없음."""
    votes = {"A": 0, "B": 0}
    for ev in evals:
        w = ev.get("predicted_winner", "?")
        c = ev.get("confidence", 1)
        if w in votes:
            votes[w] += c
    return "A" if votes["A"] > votes["B"] else "B"


def run():
    with open(_CASES_PATH) as f:
        cases = json.load(f)

    random.seed(42)
    swap_flags = [random.choice([True, False]) for _ in cases]

    logger.info("Swap flags: %s", swap_flags)

    all_results = []
    correct = 0
    total = len(cases)
    total_tokens = 0

    for i, (case, swap) in enumerate(zip(cases, swap_flags)):
        shuffled, actual_winner = shuffle_case(case, swap)

        logger.info(
            "=== [%d/%d] %s (swap=%s, actual=%s) ===",
            i + 1, total, case["id"], swap, actual_winner
        )

        evals = []
        for pid, persona in PERSONAS.items():
            ev = evaluate_case(shuffled, pid, persona)
            evals.append(ev)
            tokens = ev.get("tokens", {})
            total_tokens += tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
            logger.info("  %s → %s (conf %s)", pid, ev.get("predicted_winner"), ev.get("confidence"))

        predicted = aggregate_prediction(evals)
        match = predicted == actual_winner

        if match:
            correct += 1
            logger.info("  ✓ CORRECT — predicted %s, actual %s", predicted, actual_winner)
        else:
            logger.info("  ✗ WRONG — predicted %s, actual %s", predicted, actual_winner)

        # 세그먼트 분기 감지
        winners_set = set(ev.get("predicted_winner") for ev in evals if ev.get("predicted_winner") in ("A", "B"))
        segment_divergence = len(winners_set) > 1

        all_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "test_description": case["test_description"],
            "swapped": swap,
            "actual_winner": actual_winner,
            "lift_pct": case["lift_pct"],
            "predicted_winner": predicted,
            "match": match,
            "segment_divergence": segment_divergence,
            "persona_evaluations": evals,
        })

    accuracy = correct / total if total > 0 else 0

    # 세부 분석
    swapped = [r for r in all_results if r["swapped"]]
    unswapped = [r for r in all_results if not r["swapped"]]
    divergent = [r for r in all_results if r["segment_divergence"]]

    summary = {
        "total_cases": total,
        "correct": correct,
        "accuracy_pct": round(accuracy * 100, 1),
        "personas_used": list(PERSONAS.keys()),
        "swapped_accuracy_pct": round(sum(1 for r in swapped if r["match"]) / len(swapped) * 100, 1) if swapped else 0,
        "unswapped_accuracy_pct": round(sum(1 for r in unswapped if r["match"]) / len(unswapped) * 100, 1) if unswapped else 0,
        "segment_divergence_count": len(divergent),
        "segment_divergence_pct": round(len(divergent) / total * 100, 1),
        "results": all_results,
    }

    with open(_RESULTS_PATH, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("OVERALL ACCURACY: %d/%d = %.1f%%", correct, total, accuracy * 100)
    logger.info("SWAPPED: %.1f%% | UNSWAPPED: %.1f%%",
                summary["swapped_accuracy_pct"], summary["unswapped_accuracy_pct"])
    logger.info("SEGMENT DIVERGENCE: %d/%d cases (%.1f%%)",
                len(divergent), total, summary["segment_divergence_pct"])
    logger.info("Results → %s", _RESULTS_PATH)

    return summary


if __name__ == "__main__":
    # Constitution §6.2: H2/H3 검증 시 cache OFF 필수. 명시적으로 비활성화.
    # (provider_router.call 경로는 실제로 캐시를 사용하지 않지만, 엄밀성을 위해 명시)
    with cache_disabled():
        run()
