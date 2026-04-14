# Golden Sessions — 회귀 검증 표준 세트

> **용도**: 프롬프트 버전 변경 시 v_N-1 vs v_N 회귀 비교의 기준 데이터
> **규칙**: 한 번 정의되면 수정하지 않음 (변경은 append-only)

## 구조

```
experiments/golden_sessions/
  ├── README.md              (본 문서)
  ├── golden_01_*.json        ...
  └── golden_05_*.json
```

각 golden session은 다음 필드를 포함:

| 필드 | 용도 |
|---|---|
| `golden_id` | `golden_NN_slug` 형식 |
| `persona_id` | 사용할 페르소나 |
| `url` | 대상 URL |
| `task` | 페르소나에 부여할 태스크 |
| `expected_behavior` | 정성적 예상 행동 (자유기술) |
| `expected_outcome` | 예상 outcome (task_complete / max_turns_hit / abandoned) |
| `expected_turn_range` | 예상 턴 수 (min~max) |
| `critical_actions` | 반드시 수행해야 할 액션 목록 |
| `forbidden_actions` | 수행하면 안 되는 액션 목록 |

## 실행 방법

```python
from modules.agent_loop import run_session
from modules.review_agent import compare

# v001 vs v002 회귀 비교
compare(
    version_a="prompts/agent/decision_judge/v001",
    version_b="prompts/agent/decision_judge/v002",
    on="experiments/golden_sessions/",
)
```

## 통과 기준

- 모든 critical_actions 수행됨
- forbidden_actions 수행 없음
- outcome이 expected_outcome과 일치
- 턴 수가 expected_turn_range 내

실패 시 해당 프롬프트 변경은 롤백 대상.

## 세트 구성

| # | 페르소나 | 사이트 타입 | 태스크 |
|---|---|---|---|
| 01 | p_impulsive | 이커머스 랜딩 | 가격 확인 후 CTA 클릭 |
| 02 | p_cautious | SaaS 랜딩 | 신뢰 정보 확인 후 결정 |
| 03 | p_budget | 가격 페이지 | 최저 플랜 비교 |
| 04 | p_pragmatic | SaaS 기능 페이지 | 기능 파악 후 무료 체험 |
| 05 | p_senior | 이커머스 상품 | 전화 번호 찾기 |
