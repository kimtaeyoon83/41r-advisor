# persona_agent

Calibrated-persona analysis engine. Reusable Python package extracted from the
41R research repo for embedding in external services.

## Status

**0.2.0.dev0 — PR-1~22 완료.** 공개 API 전체 라이브, Browser 모드 SPA-친화적 진화,
Predicate scoring 신뢰도 게이트.

### 공개 API

```python
# 세션 실행
from persona_agent.lowlevel import run_session, run_cohort

# 가설 기반 진단 (planner + rewriter + aggregator)
from persona_agent.lowlevel import plan_and_run_hypothesis

# 페르소나 관리
from persona_agent.lowlevel import (
    create_persona, read_persona, list_personas,
    append_observation, append_reflection,
)

# 신뢰도 채점 (PR-22)
from persona_agent.lowlevel import score_session_predicates, ScoreResult

# 감사
from persona_agent.lowlevel import audit_report, audit_numbers, audit_pvalues

# 분석
from persona_agent.lowlevel import (
    validate_predictions,       # CATE
    run_meta, render_meta_markdown,  # cross-cohort meta
    get_baseline, diagnose_cohort,   # external benchmark
)

# 구성
from persona_agent import Settings, Workspace, configure
```

### 주요 기능 (PR 누적)

| PR | 핵심 | 해결한 문제 |
|---|---|---|
| PR-1~6 | 패키지 스켈레톤 + 모듈 이동 + Settings/extras 확립 | CWD 커플링 제거, SaaS import 가능 |
| PR-15 | Vision clicker (Claude tool_use API) + JS fallback fill | F009 selector 실패 해결 |
| PR-16 | Post-action settling + repetition detector | SPA 재렌더 대응 |
| PR-17 | API 500 retry + exponential backoff | transient crash 방지 |
| PR-18 | Hard guardrail (force break repetition) | 무한 루프 탈출 |
| PR-19 | Patience budget (soul.patience × 60s) | 페르소나별 이탈 시점 반영 |
| PR-20 | JS smart selector (DOM scoring) | SPA input 필드 정밀 접근 |
| PR-21 | Per-action 60s timeout | runner 내부 hang 방지 |
| **PR-22** | **Predicate-based scoring** | **신뢰도 정량 측정 (text·browser 통합)** |

## Layout

```
src/persona_agent/
├── __init__.py       # facade — public API
├── lowlevel.py       # power-user re-exports (모든 기능)
├── settings.py       # Settings dataclass
├── workspace.py      # Workspace + get_workspace/configure
├── errors.py         # exception hierarchy
├── _internal/
│   ├── session/      # agent_loop, browser_runner, vision_clicker, selector_memory
│   ├── persona/      # persona_store, persona_generator, schema_validator
│   ├── cohort/       # cohort_runner, cohort_report
│   ├── analysis/     # cate_validator, cross_cohort_meta, benchmark_loader, predicate_scorer
│   ├── integrity/    # hallucination_guard, claim_tagger, provenance
│   ├── reports/      # report_gen, report_analyzer, review_agent
│   ├── hypothesis/   # planner, task_rewriter, aggregator, orchestrator
│   └── core/         # provider_router, cache, events_log, metrics, hooks
└── data/             # bundled prompts, config, built-in personas
```

## 환경 변수

```bash
export PERSONA_AGENT_MAX_TURNS=20          # SPA 대응
export PERSONA_AGENT_ACTION_TIMEOUT=60     # PR-21 hang 방지
export PERSONA_AGENT_PATIENCE_MULTIPLIER=60  # PR-19 patience budget
```

## Install (dev)

```bash
pip install -e "./persona_agent[dev]"
cd persona_agent && pytest  # 169+ tests
```

## Extras

```toml
[project.optional-dependencies]
browser   = ["playwright>=1.49.0"]
reports   = ["weasyprint>=62.0"]
analysis  = ["numpy>=1.26", "scipy>=1.11"]
benchmark = ["pandas>=2.0"]
```

## Browser vs Text 모드 역할 분리 (중요)

두 모드는 **다른 것을 측정**한다:

| | Text (Primary) | Browser (Secondary) |
|---|---|---|
| 측정 | 페르소나 **인지 경험** | UI **접근성·자동화 친화도** |
| 결론 | 세그먼트 분기·UX 개선안 | 접근성 감사 |

Browser 결과 단독 해석 금지. PR-22 `score_session_predicates()`로 신뢰도
(`persona_faithfulness`) 체크하고, **0.7 미만 세션은 진단 근거에서 제외**.

상세: [`BROWSER_MODE_REVIEW.md`](./BROWSER_MODE_REVIEW.md)

## Predicate 스코어링 (PR-22)

페르소나 soul에 `predicates:` 필드 추가 → 세션 로그를 verifiable rule로 채점:

```yaml
---
name: 크립토 숙련자
predicates:
  - id: quick_ui_grasp
    type: rule
    rule: "turn_count < 10"
  - id: minimal_reading
    type: rule
    rule: "action_count('read') < 3"
---
```

```python
from persona_agent.lowlevel import score_session_predicates
result = score_session_predicates("p_crypto_native", session_log)
print(f"faithfulness = {result.persona_faithfulness:.2f}")
```

Jupiter v6 실증: p_crypto_native가 0.50 faithfulness로 최하위 → browser 모드가
숙련자 트레이트를 왜곡한다는 가설 정량 확인.

## 참고

- 전체 리팩터 플랜: `/home/kimtayoon/.claude/plans/sorted-giggling-puzzle.md`
- 사업용 리포트 템플릿: `41r/experiments/public_analysis/JUPITER_UX_DIAGNOSIS.md`
