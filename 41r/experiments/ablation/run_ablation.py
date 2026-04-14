"""Ablation Study — 개인 페르소나 프로필의 Marginal Value 검증.

2 arms:
- Arm A (baseline): Demo-only 페르소나 (나이/성별/지역/직업만)
- Arm B (41R): Demo + Persona (성향 5축 + 트리거 + 트러스트)

같은 12건 A/B 케이스 × 같은 LLM × 같은 seed. 차이는 페르소나 soul 내용뿐.

사용법:
    ANTHROPIC_API_KEY=... python3 experiments/ablation/run_ablation.py
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
_CASES_PATH = _BASE.parent / "ab_validation" / "cases.json"
_RESULTS_PATH = _BASE / "results_ablation.json"

# === ARM B: 41R (Demo + 성향 프로필) ===
PERSONAS_B = {
    "p_impulsive": {
        "name": "충동형 민수 (28세, 스타트업 마케터)",
        "soul": """- 인내심: 2초, 결정속도: 0.5초, 시각의존: 0.9, 리서치: 0.1
- 가격민감도: 0.3, 프라이버시: 0.2, 소셜프루프: 0.7
- 신뢰: 별점, 후기사진, 할인배너 / 무시: 회사연혁, 인증서
- 좌절: 느린로딩, 팝업, 강제가입, 스크롤3회+""",
    },
    "p_cautious": {
        "name": "신중형 지영 (35세, 회계법인 시니어)",
        "soul": """- 인내심: 10초, 결정속도: 3초, 시각의존: 0.3, 리서치: 0.95
- 가격민감도: 0.6, 프라이버시: 0.8, 소셜프루프: 0.5
- 신뢰: 회사연혁5년+, 고객사례3+, 환불정책, 리뷰100+ / 무시: 할인배너, 한정수량, 타이머
- 좌절: 가격숨김, 환불불명확, 리뷰부족, 회사정보없음""",
    },
    "p_budget": {
        "name": "가격민감형 현주 (32세, 교사)",
        "soul": """- 인내심: 5초, 결정속도: 2초, 시각의존: 0.5, 리서치: 0.7
- 가격민감도: 0.95, 프라이버시: 0.5, 소셜프루프: 0.6
- 신뢰: 가격투명성, 환불보장, 무료체험, 할인코드 / 무시: 브랜드스토리, 디자인어워드
- 좌절: 가격안보임, 숨은수수료, 자동결제, 불투명할인, 비교불가요금제""",
    },
    "p_pragmatic": {
        "name": "실용주의형 준혁 (42세, IT팀장)",
        "soul": """- 인내심: 6초, 결정속도: 1.5초, 시각의존: 0.5, 리서치: 0.6
- 가격민감도: 0.5, 프라이버시: 0.4, 소셜프루프: 0.4
- 신뢰: 구체적수치, 고객사로고, 기술스펙, API문서 / 무시: 감성카피, 예쁜일러스트
- 좌절: 과장마케팅, 기능숨김, 비교표없음, 불필요단계""",
    },
    "p_senior": {
        "name": "시니어 영숙 (58세, 공무원)",
        "soul": """- 인내심: 15초, 결정속도: 5초, 시각의존: 0.7, 리서치: 0.5
- 가격민감도: 0.7, 프라이버시: 0.7, 소셜프루프: 0.8, 브랜드충성: 0.9
- 신뢰: 전화번호, 오래된회사, 지인추천, TV브랜드 / 무시: 트렌디디자인, SNS팔로워
- 좌절: 작은글씨, 클릭위치불명, 영어많음, 팝업, 뒤로가기초기화
- 테크문해력: 0.3, 단순한페이지선호, 큰버튼선호""",
    },
}

# === ARM A: Demo-only Baseline (성향 축 제거) ===
PERSONAS_A = {
    "demo_young_m": {
        "name": "28세 남성 직장인 (서울)",
        "soul": "28세 남성, 서울 거주, 직장인. 한국 20대 후반 남성 직장인의 일반적인 온라인 행동 패턴을 따른다.",
    },
    "demo_adult_f": {
        "name": "35세 여성 사무직 (서울)",
        "soul": "35세 여성, 서울 거주, 사무직 직장인. 한국 30대 중반 여성 직장인의 일반적인 온라인 행동 패턴을 따른다.",
    },
    "demo_adult_f2": {
        "name": "32세 여성 교사 (인천)",
        "soul": "32세 여성, 인천 거주, 중학교 교사. 한국 30대 초반 여성 전문직의 일반적인 온라인 행동 패턴을 따른다.",
    },
    "demo_adult_m": {
        "name": "42세 남성 IT관리자 (서울)",
        "soul": "42세 남성, 서울 거주, IT 기업 관리자. 한국 40대 초반 남성 전문직의 일반적인 온라인 행동 패턴을 따른다.",
    },
    "demo_senior_f": {
        "name": "58세 여성 공무원 (부산)",
        "soul": "58세 여성, 부산 거주, 공무원. 한국 50대 후반 여성의 일반적인 온라인 행동 패턴을 따른다. 디지털 서비스 사용 경험이 20·30대 대비 제한적이다.",
    },
}

# 동일 시스템 프롬프트 (양 arm)
EVALUATION_SYSTEM = """당신은 UX 행동 예측 전문가입니다.

A/B 테스트의 두 variant 설명을 보고, 주어진 페르소나가 어느 variant에서 더 높은 확률로 전환(가입, 구매, 클릭 등)할지 예측합니다.

## 규칙
1. 페르소나의 프로필에 근거하여 판단
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
{persona["soul"]}

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
    votes = {"A": 0, "B": 0}
    for ev in evals:
        w = ev.get("predicted_winner", "?")
        c = ev.get("confidence", 1)
        if w in votes:
            votes[w] += c
    return "A" if votes["A"] > votes["B"] else "B"


def run_arm(arm_name, personas, cases, swap_flags):
    """한 arm 실행."""
    arm_results = []
    correct = 0

    for i, (case, swap) in enumerate(zip(cases, swap_flags)):
        shuffled, actual_winner = shuffle_case(case, swap)
        logger.info("[Arm %s][%d/%d] %s (swap=%s, actual=%s)",
                    arm_name, i + 1, len(cases), case["id"], swap, actual_winner)

        evals = []
        for pid, persona in personas.items():
            ev = evaluate_case(shuffled, pid, persona)
            evals.append(ev)
            logger.info("  %s → %s (conf %s)", pid, ev.get("predicted_winner"), ev.get("confidence"))

        predicted = aggregate_prediction(evals)
        match = predicted == actual_winner

        if match:
            correct += 1

        winners = set(e.get("predicted_winner") for e in evals if e.get("predicted_winner") in ("A", "B"))
        divergence = len(winners) > 1

        arm_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "test_description": case["test_description"],
            "swapped": swap,
            "actual_winner": actual_winner,
            "lift_pct": case["lift_pct"],
            "predicted_winner": predicted,
            "match": match,
            "segment_divergence": divergence,
            "persona_evaluations": evals,
        })

    accuracy = correct / len(cases) if cases else 0
    divergence_count = sum(1 for r in arm_results if r["segment_divergence"])

    return {
        "arm": arm_name,
        "accuracy": round(accuracy * 100, 1),
        "correct": correct,
        "total": len(cases),
        "divergence_count": divergence_count,
        "divergence_pct": round(divergence_count / len(cases) * 100, 1),
        "results": arm_results,
    }


def run():
    with open(_CASES_PATH) as f:
        cases = json.load(f)

    # v3와 동일한 swap 시드
    random.seed(42)
    swap_flags = [random.choice([True, False]) for _ in cases]
    logger.info("Swap flags: %s", swap_flags)

    # Arm A: Demo-only
    logger.info("=" * 70)
    logger.info("ARM A: Demo-only Baseline")
    logger.info("=" * 70)
    arm_a = run_arm("A", PERSONAS_A, cases, swap_flags)

    # Arm B: Demo + Persona (41R)
    logger.info("=" * 70)
    logger.info("ARM B: Demo + Persona (41R)")
    logger.info("=" * 70)
    arm_b = run_arm("B", PERSONAS_B, cases, swap_flags)

    summary = {
        "design_doc": "experiments/ablation/DESIGN.md",
        "seed": 42,
        "cohort_size_per_arm": 5,
        "total_cases": len(cases),
        "arm_a_demo_only": {
            "accuracy_pct": arm_a["accuracy"],
            "correct": arm_a["correct"],
            "divergence_pct": arm_a["divergence_pct"],
        },
        "arm_b_41r": {
            "accuracy_pct": arm_b["accuracy"],
            "correct": arm_b["correct"],
            "divergence_pct": arm_b["divergence_pct"],
        },
        "delta_accuracy_pp": round(arm_b["accuracy"] - arm_a["accuracy"], 1),
        "delta_divergence_pp": round(arm_b["divergence_pct"] - arm_a["divergence_pct"], 1),
        "arm_a_results": arm_a["results"],
        "arm_b_results": arm_b["results"],
    }

    with open(_RESULTS_PATH, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 70)
    logger.info("ABLATION RESULTS")
    logger.info("=" * 70)
    logger.info("Arm A (Demo-only):       %.1f%% accuracy | %.1f%% divergence",
                arm_a["accuracy"], arm_a["divergence_pct"])
    logger.info("Arm B (Demo + Persona):  %.1f%% accuracy | %.1f%% divergence",
                arm_b["accuracy"], arm_b["divergence_pct"])
    logger.info("Delta (B - A):           %+.1f%%p accuracy | %+.1f%%p divergence",
                summary["delta_accuracy_pp"], summary["delta_divergence_pp"])
    logger.info("Results → %s", _RESULTS_PATH)

    return summary


if __name__ == "__main__":
    with cache_disabled():
        run()
