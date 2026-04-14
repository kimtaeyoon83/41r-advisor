"""메트릭 3: 이유(reasoning) 구체성 blinded 평가.

양 arm의 reasoning 텍스트를 arm 식별 없이 LLM에게 점수화 요청.
1~5 스케일: 구체성, 액션가능성, 근거 명확성.

편향 방지:
- 각 케이스의 (A_reasoning, B_reasoning) 순서를 랜덤 섞음
- Arm 정보 제거
- 이유 텍스트만 입력
"""

import json
import logging
import random
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE.parent.parent))

from core.cache import cache_disabled
from core.provider_router import call as llm_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_RESULTS = _BASE / "results_ablation.json"
_OUT = _BASE / "metric_3_specificity.json"

SCORING_SYSTEM = """당신은 UX 리서치 리뷰어입니다.

두 유저 행동 예측 설명(Explanation 1, Explanation 2)을 보고, 각각을 1~5로 점수화하세요.

## 평가 기준
- **구체성(specificity)**: 일반론이 아닌 구체적 요소(숫자, 트리거, 행동)를 언급하는가
- **액션가능성(actionability)**: PM/CPO가 이 설명을 보고 바로 개선 액션을 도출할 수 있는가
- **근거 명확성(grounding)**: "왜 그렇게 예측했는지" 프로필 기반 근거가 명확한가

## 점수
- 5: 매우 구체적, 액션가능, 근거 명확
- 4: 구체적, 대부분 액션가능
- 3: 일반적이지만 방향은 맞음
- 2: 모호함
- 1: 무의미/동어반복

## 출력 (JSON만)
{
  "explanation_1_score": 1~5,
  "explanation_2_score": 1~5,
  "winner": "1" 또는 "2" 또는 "tie",
  "reasoning": "왜 그렇게 점수를 매겼는지 1문장"
}

어느 것이 Arm A인지 Arm B인지 모르는 상태로 공정하게 평가하세요."""


def score_pair(case_desc: str, exp1: str, exp2: str) -> dict:
    user_msg = f"""## 테스트 맥락
{case_desc}

## Explanation 1
{exp1}

## Explanation 2
{exp2}

두 설명을 점수화해주세요."""

    response = llm_call(
        "review_proposer",
        [{"role": "user", "content": user_msg}],
        system=SCORING_SYSTEM,
        max_tokens=512,
    )

    raw = response.get("content", "")
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except json.JSONDecodeError:
        pass
    return {"explanation_1_score": 0, "explanation_2_score": 0, "winner": "parse_error", "reasoning": raw[:200]}


def main():
    with open(_RESULTS) as f:
        data = json.load(f)

    arm_a = data["arm_a_results"]
    arm_b = data["arm_b_results"]

    random.seed(42)

    scores = []
    a_total, b_total, count = 0, 0, 0

    for ra, rb in zip(arm_a, arm_b):
        # 각 케이스: 페르소나별 reasoning을 이어붙여 arm 전체 설명으로 만듦
        reasoning_a = "\n".join(f"- {e.get('reasoning', '')}" for e in ra["persona_evaluations"])
        reasoning_b = "\n".join(f"- {e.get('reasoning', '')}" for e in rb["persona_evaluations"])

        # 랜덤 순서 결정 (편향 방지)
        swap = random.choice([True, False])
        if swap:
            exp1, exp2 = reasoning_b, reasoning_a
            label_1, label_2 = "B", "A"
        else:
            exp1, exp2 = reasoning_a, reasoning_b
            label_1, label_2 = "A", "B"

        case_desc = f"{ra['test_description']} | 실제 승자: {ra['actual_winner']}"
        logger.info("Scoring %s (order=%s)", ra["case_id"], f"{label_1},{label_2}")

        result = score_pair(case_desc, exp1, exp2)

        # 라벨 되돌리기
        s1 = result.get("explanation_1_score", 0)
        s2 = result.get("explanation_2_score", 0)
        a_score = s1 if label_1 == "A" else s2
        b_score = s2 if label_2 == "B" else s1

        # winner 되돌리기
        w = result.get("winner", "tie")
        if w == "1":
            arm_winner = label_1
        elif w == "2":
            arm_winner = label_2
        else:
            arm_winner = "tie"

        scores.append({
            "case_id": ra["case_id"],
            "arm_a_score": a_score,
            "arm_b_score": b_score,
            "winner_arm": arm_winner,
            "order_presented": f"{label_1},{label_2}",
            "judge_reasoning": result.get("reasoning", ""),
        })

        a_total += a_score
        b_total += b_score
        count += 1

    avg_a = a_total / count if count else 0
    avg_b = b_total / count if count else 0
    b_wins = sum(1 for s in scores if s["winner_arm"] == "B")
    a_wins = sum(1 for s in scores if s["winner_arm"] == "A")
    ties = sum(1 for s in scores if s["winner_arm"] == "tie")

    summary = {
        "metric": "specificity_blinded",
        "judge_model": "claude-sonnet-4-6",
        "total_cases": count,
        "arm_a_avg_score": round(avg_a, 2),
        "arm_b_avg_score": round(avg_b, 2),
        "delta": round(avg_b - avg_a, 2),
        "head_to_head": {
            "arm_b_wins": b_wins,
            "arm_a_wins": a_wins,
            "ties": ties,
        },
        "scores": scores,
    }

    with open(_OUT, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("METRIC 3: Reasoning Specificity (Blinded)")
    print("=" * 70)
    print(f"Arm A avg score: {avg_a:.2f}")
    print(f"Arm B avg score: {avg_b:.2f}")
    print(f"Delta: {avg_b - avg_a:+.2f}")
    print(f"Head-to-head: B wins {b_wins}, A wins {a_wins}, ties {ties}")
    print(f"Saved: {_OUT}")


if __name__ == "__main__":
    with cache_disabled():
        main()
