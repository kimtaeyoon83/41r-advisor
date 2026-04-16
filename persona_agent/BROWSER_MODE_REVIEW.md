# Browser Mode Review — PR-15 ~ PR-22 누적 현황

> 최종 업데이트: 2026-04-16 (PR-22 predicate scoring 적용 + Jupiter v6 검증 완료)

persona_agent 0.2.0의 browser 모드(`run_session(mode="browser")`)가 PR-15부터
PR-22까지 누적 8개 PR로 SPA-친화적으로 진화 + 신뢰도 정량 측정 프레임워크 확립.
본 문서는 **현재 capability 한눈에 보기** + **남은 한계** + **다음 단계 후보**를 정리.

---

## 1. 현재 Browser 모드 계층

```
run_session(persona_id, url, task, max_turns=20)
  │
  ├── agent_loop (PR-19 patience check at loop top)
  │   └── while not done and turn < turn_limit:
  │       ├── patience_budget check  ← soul.patience_seconds × 60
  │       ├── get_state (A11y + screenshot + PR-16 nav_hints if A11y empty)
  │       ├── repetition_detect (PR-16 soft signal)
  │       ├── decide (LLM with repetition_warning in context)
  │       ├── select_tool
  │       ├── force_break_repetition (PR-18 hard guardrail)
  │       ├── run_action  ← 아래 layer
  │       └── observation + event logs
  │
  └── browser_runner._exec_action (PR-21 timeout wrapper)
      └── asyncio.wait_for(_exec_action_inner, timeout=60s)
          ├── wait_network_idle + dismiss_overlay
          ├── _dispatch (9 primitive actions)
          │   ├── click
          │   │   ├── text selector chain (6 strategies)
          │   │   ├── PR-20 _js_smart_find (DOM scoring)
          │   │   ├── a11y_match (semantic)
          │   │   └── PR-15 vision_clicker (Claude tool_use coordinates)
          │   └── fill
          │       ├── locator.fill
          │       ├── PR-15 vision_fill
          │       └── PR-15 _js_fallback_fill (DOM injection)
          ├── PR-16 post-action settling (800ms + networkidle 2s)
          └── before/after diff
```

모든 LLM 호출은 `provider_router.call()`을 거치며 PR-17 retry wrapper 적용.

---

## 2. PR별 기여 요약

| PR | 핵심 변경 | 해결한 문제 | 검증 |
|---|---|---|---|
| **PR-15** | vision_clicker → Claude tool_use API | JSON 파싱 실패 (F009 근본) | v3: F009 15+→0~1 |
| **PR-15** | MAX_TURNS 파라미터화 | 10턴 제한으로 SPA 미완주 | 기본 10, run_session(max_turns=20) |
| **PR-15** | JS fallback fill (canvas input) | React controlled component 입력 실패 | v3: fill 0→1건 성공 |
| **PR-16** | Post-action settling (800ms) | SPA 재렌더 미완 상태에서 다음 action | 별도 측정 없음 (기본 동작) |
| **PR-16** | Repetition detector (soft signal) | LLM이 같은 action 반복 | v3: rep_warn 2회 발동 |
| **PR-16** | JS nav hints (a11y 빈약 시) | SPA 진입점 미발견 | 발동은 했지만 효과 측정 미완 |
| **PR-17** | Anthropic API 500 retry + exp backoff | 3/5 세션 transient crash | v4: 5/5 세션 실행 |
| **PR-18** | Plan 프롬프트 강화 + hard guardrail | Settings close 반복 루프 | 단위 테스트 통과, 실전 영향 미측정 |
| **PR-19** | Persona patience 기반 auto-abandon | "도구가 오래 시도 → 성공" artifact | v5: 저patience 2~8턴 이탈 |
| **PR-20** | JS smart selector (DOM scoring) | Playwright 기본 selector가 SPA input 못 잡음 | v5: p_senior 19→15턴 단축 |
| **PR-21** | Per-action timeout (60s 기본, F010) | runner.run_action 내부 hang 탈출 불가 | 단위 테스트 4건, v6에서 55분 hang 재현 없음 확인 |
| **PR-22** | Predicate-based scoring framework | text·browser 통합 측정 + 신뢰도 게이트 | 단위 테스트 13건, Jupiter v6 30 세션 채점 완료 |

**누적 효과** (Jupiter 기준):
- v2 (pre-PR-15): 5/5 전원 이탈, F009 15+회, fill 0건
- v4 (PR-15~18): 5/5 유효, 1건 task_complete, F009 7회, fill 7건
- v5 (PR-15~20): 5/5 유효, 1건 task_complete, F009 6회, fill 3건, **patience 강제로 text 예측 수렴**
- v6 (PR-15~21): **25 runs 전원 완주, Turn 1 hang 재현 없음, task_complete 1건**
- v6 + PR-22 적용: **persona_faithfulness 정량 확인** — p_senior 0.87 (트레이트 일치) vs p_crypto_native 0.50 (왜곡). 도구가 숙련자 트레이트를 override함을 수치로 증명.

---

## 3. Capability 매트릭스

| 시나리오 | PR-15 이전 | 현재 (PR-21 포함) |
|---|---|---|
| 정적 HTML 사이트 (example.com) | ✅ 작동 | ✅ 작동 |
| 일반 SaaS 랜딩 (Notion/Slack pricing) | ✅ 작동 | ✅ 작동 |
| 한국 e-commerce (musinsa, coupang) | ✅ 대체로 | ✅ 대체로 |
| **복잡 SPA dApp (Jupiter, Raydium)** | ❌ F009 대부분 | 🟡 부분 작동 (1/5 완주) |
| Canvas/SVG 기반 input | ❌ selector 실패 | 🟡 JS fallback으로 부분 해결 |
| Vision 좌표 추출 한국어 target | ❌ JSON 파싱 실패 | ✅ tool_use로 안정 |
| 지갑 연결 필수 dApp (실제 swap) | ❌ 불가 | ❌ 여전히 불가 (Phantom 확장 없음) |
| 장시간 hang 복구 | ❌ 수동 kill 필요 | ✅ PR-21 60s timeout |
| 반복 루프 탈출 | ❌ 무한 반복 | ✅ PR-16/18로 해결 |
| 저patience 페르소나 빠른 이탈 | ❌ 페르소나 특성 무시 | ✅ PR-19 patience budget |

---

## 4. 남은 한계

### 4.1 근본적 한계 (도구 아키텍처 차원)

- **Phantom/MetaMask 확장 없음** → 실제 blockchain transaction 불가. dApp의 "Connect Wallet" 이후는 측정 불가.
- **도구 성공 ≠ 페르소나 성공** — PR-19가 patience 차원은 해결했지만, **인지 마찰**(슬리피지 의미 모름, 경고 맥락 못 읽음)은 여전히 도구 관점에선 "LLM이 역할 연기"로 극복 가능. 실사용자와 동일하게 측정하려면 predicate-based scoring 필요 (§ 5.2).

### 4.2 기술적 한계

- **Canvas-rendered input** — PR-15의 JS fallback은 대부분 React controlled component 커버하지만, canvas 기반 UI (일부 TradingView 차트 등)는 여전히 불가.
- **OAuth/Captcha** — 측정 대상 외.
- **네트워크 idle 타임아웃** — jup.ag 같은 실시간 가격 업데이트 사이트는 네버 idle. PR-16 settling의 networkidle 대기가 2s로 제한되어 있으나 여전히 보수적.

### 4.3 측정 한계

- **"text vs browser" 괴리** — § ARCHITECTURE.md § 11.3 참조. 둘은 다른 것을 측정한다고 명시했지만, **사업 담당자가 어느 쪽을 "정답"으로 봐야 하는지 여전히 모호**.
- **단일 세션 per persona** — 통계 유의성 낮음. 표본 확대 필요 (persona당 3~5회 반복).

---

## 5. 다음 단계 후보 (우선순위)

### 5.1 즉시 검증 가능 (1일 이내)

- **Jupiter v6 실행** — PR-21 per-action timeout 포함. v5의 p_b2b_buyer Turn 1 hang 재발 여부 확인. 완전한 5/5 유효 데이터 기대.
- **다른 dApp** (Raydium, Orca) — Jupiter와 비교. 같은 cohort로 "어느 dApp이 비숙련자에게 덜 어려운가" 진단.

### 5.2 측정 프레임워크 개선 (완료 — PR-22)

✅ **Predicate-based scoring** — text·browser 통합 측정.
- 페르소나 soul YAML에 `predicates: [{id, type, rule, description}]` 필드 추가
- rule-based (빠름·무료) + llm-based (복잡 맥락) 하이브리드
- 세션 로그를 predicate로 채점 → `persona_faithfulness` (passed / total - skipped)
- **신뢰도 게이트**: faithfulness < 0.7 세션은 진단 근거에서 제외 또는 보조로만

**Jupiter v6 적용 결과 (2026-04-16)**:

| Persona | faithfulness | 해석 |
|---|---:|---|
| p_senior | 0.87 | 트레이트 일치 |
| p_b2b_buyer | 0.80 | 트레이트 일치 |
| p_pragmatic | 0.67 | 중간 |
| p_creator_freelancer | 0.60 | 중간 |
| p_crypto_native | **0.50** | **트레이트 왜곡** |

**핵심 통찰**: p_crypto_native의 낮은 faithfulness는 **"숙련자 페르소나가 20턴·1000초 세션을 진행한다"는 browser 결과가 트레이트와 맞지 않음**을 정량 증명. 도구·LLM이 페르소나 트레이트를 override하고 역할 연기로 진행한 증거.

**활용 규칙**:
- faithfulness ≥ 0.8: 진단 근거로 신뢰 가능
- 0.7 ≤ faithfulness < 0.8: 보조 증거, text mode cross-check 필수
- faithfulness < 0.7: 진단 근거에서 제외

**공개 API**: `from persona_agent.lowlevel import score_session_predicates, PredicateResult, ScoreResult`

### 5.3 도구 경쟁력 확장 (장기, 2~4주)

- **AgentQL 통합 검토** (vision_clicker 추가 대체)
- **Anthropic Computer Use API** 실험 (우리 vision_clicker vs. 네이티브)
- **Stagehand Python SDK** 평가 (41rpm autotest.ts와 동일 도구)

---

## 6. 사업 담당자 전달용 요약 (1줄)

> "persona_agent 0.2.0 browser 모드는 7개 PR 누적으로 Jupiter 같은 복잡 SPA에서도
> **부분 작동**하는 수준이나, 여전히 **text 모드가 세그먼트 진단의 primary**.
> Browser는 **UI 접근성 보조 감사** + **실측 증거 수집** 목적으로 활용."

---

## Appendix — 파일 위치

- 핵심 구현: `persona_agent/src/persona_agent/_internal/session/`
  - `agent_loop.py` (PR-19 patience + PR-16 detector + PR-18 guardrail)
  - `browser_runner.py` (PR-21 timeout + PR-20 JS smart + PR-15 JS fill)
  - `vision_clicker.py` (PR-15 tool_use)
- LLM router: `_internal/core/provider_router.py` (PR-17 retry)
- 프롬프트: `data/prompts/agent/decision_judge/v002.md` (PR-18 루프 탈출 규칙)
- 테스트: `persona_agent/tests/test_{action_timeout,patience_budget,repetition_*,provider_router_retry,predicate_scorer}.py`
- Predicate 프레임워크: `_internal/analysis/predicate_scorer.py` + `tests/test_predicate_scorer.py` (13건)

실전 사용 시:
```bash
export PERSONA_AGENT_MAX_TURNS=20
export PERSONA_AGENT_ACTION_TIMEOUT=60  # PR-21
export PERSONA_AGENT_PATIENCE_MULTIPLIER=60  # PR-19
```

페르소나 soul에 predicates 추가 (PR-22 활용):
```yaml
---
name: 예시 페르소나
predicates:
  - id: quick_ui_grasp
    type: rule
    rule: "turn_count < 10"
    description: "숙련자는 10턴 내 결판"
---
```

세션 채점:
```python
from persona_agent.lowlevel import score_session_predicates
result = score_session_predicates("p_crypto_native", session_log)
if result.persona_faithfulness < 0.7:
    # 이 세션은 페르소나답지 않음 — 진단 근거에서 제외 고려
    ...
```
