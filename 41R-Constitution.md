# 41R Persona Market — Constitution

> **작성일**: 2026-04-12
> **버전**: Constitution v1.0 (v4 본문 + v4.1 advisor 패치 + 대화 중 확정 사항 통합)
> **성격**: "시스템이 이렇게 생겼다"의 고정 선언. Sprint 종료 시점에만 revision.
> **짝 문서**: `Slice-H1.md` — "지금 이것만 만든다"

---

## 0. 문서 체계

본 시스템은 세 계층의 문서로 운영된다.

| 문서 | 역할 | 변경 빈도 |
|---|---|---|
| **Constitution** (본 문서) | 시스템 구조, 인터페이스, 원칙의 고정 선언 | Sprint 종료 시점에만 |
| **Slice-H1** | 현재 sprint에서 실제 구현할 범위 | Sprint 단위 |
| **v4.md** (원본) | 초기 설계 레퍼런스 | 불변 |

Constitution은 AI/개발자가 코드 일관성을 유지하는 데 필요한 모든 선언을 담는다. 구현 일정과 구현 우선순위는 Slice 문서의 영역이다.

---

## 1. 시스템 본질

**입력**: 고객사의 제품 URL(들) + 태스크 + 타겟 유저 세그먼트(자연어)
**출력**: 캘리브레이션된 페르소나가 실제 브라우저에서 제품을 사용한 결과를 비교한 예측 리포트
**핵심 사용 시나리오**: 출시 전 예측 A/B 테스트 (하루 내 결과, 기존 A/B 대비 2~4주 단축)

### 기술적 차별화
- 페르소나 = **자연어 memory stream + reflection** (Stanford Park 2023 계보)
- Agent와 Persona가 **독립된 두 축으로 진화**
- 모든 관찰이 **SAS 온체인 provenance**로 증명
- 시스템이 **Review Agent + Version Manager**로 점진 개선

---

## 2. 핵심 원칙

### 🪨 Stable Core / 🔥 Hot Zone 분리

모든 코드는 두 카테고리 중 하나에 속한다.

- **Stable Core (`modules/`)**: 파일 I/O, 브라우저 러너, 루프 골격, 리포트 렌더링. 몇 달간 안 바뀜.
- **Hot Zone (`prompts/`, `config/research/`)**: 프롬프트, 튜닝 파라미터. 매일 바뀜.

**절대 규칙**: 판단 로직은 코드에 박지 않는다. 항상 Hot Zone에서 로드한다.

### Versioned Document 패턴

변경 가능한 모든 것은 동일 구조를 따른다.

```
{any_path}/
  v001.{ext}
  v002.{ext}
  manifest.yaml     # current 버전 지정 + 메타데이터
```

- 모든 변경은 새 파일 생성 (append-only, 삭제 없음)
- 롤백 = `manifest.current` 필드 변경
- 심볼릭 링크 사용 안 함 (OS 독립성)
- 각 파일은 frontmatter 메타데이터 포함

### Events Log 단일 진실의 원천

모든 의미 있는 사건은 `events/YYYY-MM-DD.jsonl`에 시간순 기록. 디버깅, 감사, Review Agent 분석의 통합 지점.

### 콘텐츠 해시 ID

모든 영구 객체(프롬프트, observation, reflection, 캐시 키)의 ID는 콘텐츠 해시. 무결성/중복제거/재현성/SAS 자연 연결을 동시에 확보.

### Persona = 시간 함수

`persona_at(persona_id, timestamp) -> Snapshot` 하나로 시간 여행. H3 플라이휠 검증의 핵심 도구.

### Reflection Immutable

Reflection은 절대 수정하지 않는다. 새 합성은 새 파일. 구 reflection은 `deprecated` 상태로 manifest에 기록.

---

## 3. 전체 구조도

```
┌──────────────────────────────────────────────────────────────┐
│                      입력 (고객)                              │
│            URL + 태스크 + 타겟 유저 세그먼트                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                     Stable Core (modules/)                   │
│                                                               │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│   │  M1      │    │  M3      │◄──►│  M2      │              │
│   │ Persona  │───►│ Agent    │    │ Browser  │              │
│   │ Store    │    │ Loop     │    │ Runner   │              │
│   └────┬─────┘    └────┬─────┘    └──────────┘              │
│        │               │                                      │
│        │               ▼                                      │
│        │          ┌──────────┐         ┌──────────┐          │
│        │          │  M4      │         │  M5      │          │
│        │          │ Provenance│────────►│ Report   │─────────►
│        │          │ (stub)   │         │ Gen      │   PDF
│        │          └──────────┘         └──────────┘          │
│        │                                                      │
│        ▼                                                      │
│   ┌──────────┐    ┌──────────┐                                │
│   │  M6      │───►│  M7      │                                │
│   │ Review   │    │ Version  │                                │
│   │ Agent    │    │ Manager  │                                │
│   └──────────┘    └──────────┘                                │
│                                                               │
└──────────────────────────────────────────────────────────────┘
        ▲                                        ▲
        │                                        │
┌───────┴──────────────────┐        ┌────────────┴─────────────┐
│  Cross-cutting (core/)   │        │   Hot Zone (prompts/,    │
│                          │        │         config/research/)│
│  • Provider Router       │        │                          │
│    (3-Tier + Advisor)    │        │  • agent/plan_generator/ │
│  • Cache (plan/page/tool)│        │  • agent/decision_judge/ │
│  • Events Log            │        │  • agent/tool_selector/  │
│  • Hooks (최소)          │        │  • review/*              │
│                          │        │  • persona_templates/    │
│                          │        │  • config/llm_routing/   │
│                          │        │  • config/cache/         │
└──────────────────────────┘        └──────────────────────────┘
```

---

## 4. 디렉토리 구조

```
41r/
├── modules/                          🪨 Stable Core
│   ├── persona_store.py              M1
│   ├── browser_runner.py             M2
│   ├── agent_loop.py                 M3 (plan + loop 통합)
│   ├── provenance.py                 M4 (stub)
│   ├── report_gen.py                 M5
│   ├── review_agent.py               M6
│   ├── version_manager.py            M7
│   └── plan_cache.py                 plan 전용 캐시
│
├── core/                             🛠 Cross-cutting
│   ├── provider_router.py            3-Tier + Advisor
│   ├── cache.py                      범용 콘텐츠 해시 캐시
│   ├── events_log.py                 JSONL append
│   └── hooks.py                      최소 lifecycle
│
├── prompts/                          🔥 Hot Zone
│   ├── agent/
│   │   ├── plan_generator/           세션 시작 시 계획
│   │   ├── decision_judge/           매 턴 결정
│   │   ├── tool_selector/            액션 선택 (LOW)
│   │   ├── page_summarizer/          DOM → 요약 (LOW)
│   │   └── replan_trigger/           계획 이탈 판단
│   ├── reflection/
│   │   ├── level1_pattern/
│   │   └── level2_cross_context/
│   ├── persona_templates/
│   ├── report/
│   └── review/
│       ├── session_inspector/
│       ├── persona_consistency/
│       └── revision_proposer/
│
├── config/
│   ├── research/                     🔥 Hot Zone
│   │   ├── llm_routing/              Tier + 역할 매핑
│   │   ├── cache/                    TTL + 무효화 규칙
│   │   └── reflection_triggers/
│   └── system/                       🔒 Freddie only
│       └── api_endpoints/
│
├── personas/
│   └── p_XXX/
│       ├── soul/                     seed (versioned)
│       ├── history/                  observations (immutable)
│       ├── reflections/              immutable
│       └── snapshots/
│
├── events/                           ⭐ 단일 활동 로그
│   └── YYYY-MM-DD.jsonl
│
├── sessions/                         append-only
│
├── reports/
│   └── rpt_XXX/
│       ├── report.pdf
│       └── lineage.json
│
├── experiments/
│   ├── proposals/                    🟡 Review Agent 쓰기
│   ├── golden_sessions/              회귀 테스트 표준
│   └── ab_results/                   버전 비교 결과
│
└── cache/                            런타임 캐시
    ├── plans/
    ├── page_summaries/
    └── tool_selections/
```

---

## 5. 모듈 명세

### M1. Persona Store

```python
create_persona(persona_id, soul_text) -> None
read_persona(persona_id, at_time=None) -> PersonaState
append_observation(persona_id, obs) -> ObsID
append_reflection(persona_id, level, text, sources) -> ReflID
persona_at(persona_id, timestamp) -> PersonaSnapshot
list_personas() -> list[str]
```

**observation 필수 필드** (H2/H3 기반):
- `obs_id`, `timestamp`, `persona_id`, `persona_version`, `content`

### M2. Browser Runner

```python
start_session(url, persona_context) -> SessionHandle
run_action(session, action_text) -> ActionResult
end_session(session) -> SessionLog
get_state(session) -> PageState
```

### M3. Agent Loop

세션 내부에 **Plan 단계**와 **Loop 단계**가 통합됨.

```python
run_session(persona_id, url, task) -> SessionLog
# 내부 흐름:
#   1. plan = generate_plan(persona, task, url)     [HIGH]
#   2. while not done:
#        state = summarize_page(browser.get_state())  [LOW]
#        decision = decide(persona, plan, state)      [MID + advisor]
#        tool = select_tool(decision)                  [LOW]
#        browser.run_action(tool)
#        append_observation(...)
#        if plan_deviation: plan = replan(...)
```

**Decision 스키마**:
```
{
  action, reason, done,
  step_progress: "진행중|완료|포기",
  plan_deviation: "필요시 이유"
}
```

### M4. Provenance Recorder (stub in H1)

```python
record(data) -> TxnHash
```

### M5. Report Generator

```python
generate_report(session_logs, personas, comparison_mode) -> PDFPath
```

출력에 lineage.json 필수 포함:
- 사용된 모든 prompt 버전 (path, hash)
- 모델 라우팅 설정
- 활성 reflection
- 캐시 hit/miss 통계

### M6. Review Agent

Freddie의 수동 개선 작업을 확장하는 분석 도구. 자동화 아님.

```python
inspect(session_id) -> SessionView          # 로그 + 프롬프트 + obs 통합 뷰
evaluate(session_id) -> ConsistencyScore    # 페르소나 일관성 채점
propose(session_id, finding) -> ProposalID  # 수정안 draft 생성
compare(version_a, version_b, on=golden) -> ComparisonReport
```

모든 출력은 `experiments/proposals/`에만 쓴다. `prompts/`에 직접 쓰지 않는다.

### M7. Version Manager

H1 단계 최소 기능:

```python
save_version(path, content, author, message) -> version_id
get_current(path) -> content
get_version(path, version) -> content
rollback(path, to_version, reason) -> None
get_lineage(report_id) -> dict
```

Review Agent의 proposal이 승인되면 Version Manager만이 `prompts/`에 쓰기 권한을 가진다.

---

## 6. Cross-Cutting 컴포넌트

### 6.1 Provider Router — 3-Tier + Advisor

**Tier 정의**:

| Tier | 모델 | 용도 |
|---|---|---|
| HIGH | Opus 4.6 | 전략 판단, 계획 수립, Advisor escalate, 회귀 분석 |
| MID | Sonnet 4.6 | 실행 판단, 페르소나 시뮬, 일관성 평가 |
| LOW | Haiku 4.5 | 도구 선택, 페이지 요약, 간단한 분기 |

**역할 → Tier 매핑** (config/research/llm_routing/):

```yaml
tiers:
  high: { model: claude-opus-4-6 }
  mid:  { model: claude-sonnet-4-6 }
  low:  { model: claude-haiku-4-5 }

roles:
  plan_generation:      { tier: high, advisor: null }
  decision_judge:       { tier: mid,  advisor: high, max_advisor_uses: 3 }
  tool_selection:       { tier: low,  advisor: null }
  page_summarizer:      { tier: low,  advisor: null }
  replan_trigger:       { tier: mid,  advisor: null }
  review_inspection:    { tier: low,  advisor: null }
  review_consistency:   { tier: mid,  advisor: high, max_advisor_uses: 2 }
  review_proposer:      { tier: mid,  advisor: high, max_advisor_uses: 3 }
  review_regression:    { tier: high, advisor: null }
```

**API 통합**:

```python
provider_router.call(role="decision_judge", messages=[...])
# 내부: tier 모델로 호출, advisor 정의 있으면 advisor tool 자동 등록
```

Anthropic advisor tool (`advisor_20260301`, beta header `advisor-tool-2026-03-01`) 네이티브 활용.

### 6.2 Cache — 중복 실행 제거

**캐시 대상**:

```
cache/
  plans/            hash(persona_template + task + url_pattern)
  page_summaries/   hash(url + dom_hash)
  tool_selections/  hash(page_state_summary + decision)
```

**Plan Cache 3단계 조회**:

1. **Exact Match** `hash(persona_id + task + url)` → 그대로 반환
2. **Template Match** `hash(persona_template + task)` → 골격 재사용, LOW로 세부 조정
3. **Full Generation** → HIGH로 생성 + 캐시 저장

**무효화 규칙** (config/research/cache/):

```yaml
invalidate_on:
  prompt_version_change: true
  persona_soul_change: true
  ttl_expiry: true
not_invalidate_on:
  reflection_added: false
```

**H2/H3 검증 시 필수**: `with cache_disabled():` 모드로 실행. 캐시가 정확도 측정을 오염시키지 않도록.

### 6.3 Events Log

```jsonl
{"t":"...","type":"session_started","persona":"p_042","url":"..."}
{"t":"...","type":"plan_generated","session":"s_01","plan_id":"pl_7","source":"cache_hit"}
{"t":"...","type":"decision","persona":"p_042","prompt_ver":"v015","model":"sonnet","advisor_invoked":false}
{"t":"...","type":"decision","persona":"p_042","prompt_ver":"v015","model":"sonnet","advisor_invoked":true,"advisor":"opus"}
{"t":"...","type":"observation","persona":"p_042","obs_id":"o_8821"}
{"t":"...","type":"replan","session":"s_01","reason":"..."}
{"t":"...","type":"prompt_changed","path":"agent/decision_judge","from":"v015","to":"v016","author":"freddie"}
{"t":"...","type":"report_generated","report_id":"rpt_42"}
```

### 6.4 Hooks (최소)

H1 단계에선 `post_session_end` 하나만:

```yaml
post_session_end:
  - review_agent_inspect    # 자동 인스펙션만, 수정 제안은 Freddie 수동 트리거
```

풀 hook system은 v4-full.

---

## 7. 개선 루프 (Review ↔ Version)

```
        세션 실행
             │
             ▼
   ┌──────────────────┐
   │  M6 Review Agent │
   │                  │
   │  inspect         │ [LOW]
   │  evaluate        │ [MID, advisor=HIGH]
   │  propose         │ [MID, advisor=HIGH]
   └────────┬─────────┘
            │ draft
            ▼
   ┌─────────────────────────┐
   │ experiments/proposals/  │  🟡 Review Agent 쓰기
   │   prop_XXX.md           │
   │   (pending)             │
   └────────┬────────────────┘
            │
            ▼
       Freddie 검토
       (approve CLI)
            │
            ▼
   ┌──────────────────┐
   │ M7 Version Mgr   │  🔒 승인된 proposal만 적용
   │                  │
   │  save_version    │
   │  update manifest │
   │  log events      │
   └────────┬─────────┘
            │
            ▼
   ┌─────────────────────────┐
   │ prompts/agent/xxx/      │
   │   v016.md               │
   │   manifest: current=v016│
   └────────┬────────────────┘
            │
            ▼
     다음 세션은 v016
            │
            ▼
   ┌──────────────────┐
   │ M6 compare       │  [HIGH for regression analysis]
   │ v015 vs v016     │
   │ on golden_sessions│
   └────────┬─────────┘
            │
      나쁘면 rollback
      (manifest.current = v015)
```

**핵심 안전장치 (1인 운영 기준)**:
- Review Agent는 `proposals/`에만 쓰기
- `prompts/`는 Version Manager만 쓰기
- 둘 사이의 게이트는 Freddie의 승인 CLI
- 이 디렉토리 분리가 팀 규모 Permission system을 대체한다

---

## 8. Agent Loop 상세 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                   세션 시작 (1회)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Plan Cache 조회                                            │
│    │                                                         │
│    ├─ Exact hit   → plan 반환                               │
│    ├─ Template hit → [LOW] 세부 조정                         │
│    └─ Miss        → [HIGH] plan_generation                   │
│                     (advisor 없음, 이미 최상위)              │
│                                                              │
│   Plan = { steps[], 중단조건, 페르소나 주입 의도 }          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  매 턴 반복                                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   1. page_state 수집                                         │
│       M2.get_state() → 원본 DOM/스샷                         │
│       [LOW] page_summarizer (캐시 적용)                      │
│       → 요약된 state                                         │
│                                                              │
│   2. Decision                                                │
│       context = persona + plan + state + recent_obs          │
│       [MID] decision_judge                                   │
│         └─ 어려우면 [HIGH] advisor escalate                  │
│       → Decision { action, step_progress, plan_deviation }  │
│                                                              │
│   3. Tool selection                                          │
│       [LOW] tool_selector (캐시 적용)                        │
│       → { tool: "click"|"scroll"|..., params: {...} }       │
│                                                              │
│   4. 행동 실행                                               │
│       M2.run_action(tool)                                    │
│       → ActionResult                                          │
│                                                              │
│   5. 기록                                                    │
│       M1.append_observation (★ 필드 포함)                    │
│       events log append                                       │
│                                                              │
│   6. Replan 판단                                             │
│       if decision.plan_deviation:                            │
│         [MID] replan_trigger → new plan 또는 중단            │
│                                                              │
│   7. 종료 조건                                               │
│       done | abandon | max_turns                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. H2/H3 데이터 기반 (H1 단계에 반드시 기록)

H1 단계에서 능동 검증은 H1만이지만, 다음은 반드시 지금부터 기록한다. 빠뜨리면 H2/H3 단계에서 소급 불가.

**Observation**:
- `timestamp` (UTC, 밀리초)
- `persona_version`

**Events log**:
- `persona_version`
- `prompt_path` + `prompt_version`
- `model_name` + `tier`
- `advisor_invoked` (bool)
- `cache_hit` (bool)

**Session log**:
- 모든 세션은 immutable append-only로 저장
- 덮어쓰기 금지

---

## 10. 재현성 — Report Lineage

모든 리포트는 lineage.json을 동반한다.

```json
{
  "report_id": "rpt_20260412_042_A",
  "generated_at": "2026-04-12T14:23Z",
  "stack_versions": {
    "plan_generator":   "v003 (hash: a3f2b1c)",
    "decision_judge":   "v015 (hash: 8e4d9f2)",
    "tool_selector":    "v002 (hash: 1c7a5b3)",
    "page_summarizer":  "v004 (hash: 7d3e2a1)"
  },
  "persona_snapshot": {
    "id": "p_042",
    "soul_version": "v002",
    "last_observation": "o_142",
    "active_reflections": ["r_018", "r_021"]
  },
  "model_routing": {
    "plan_generation":  "opus-4-6",
    "decision_judge":   "sonnet-4-6 (+opus advisor)",
    "tool_selection":   "haiku-4-5"
  },
  "cache_stats": {
    "plan_cache_hit": true,
    "page_summary_hits": 14,
    "tool_selection_hits": 11
  }
}
```

---

## 11. 가설 검증 매핑

| 가설 | 검증 방법 | Kill Criteria |
|---|---|---|
| H1 바이어 | Sample report + 공개 A/B 역검증 3건 → CPO 30명 콜드 아웃바운드 | 유료 전환율 < 5% |
| H2 정확도 | Seed only vs full memory 페르소나 비교 (multi-model, **캐시 OFF**) | 상관계수 유의차 없음 |
| H3 플라이휠 | `persona_at()`로 시간별 정확도, learning curve | 100→1K 구간 saturate |
| H4 커뮤니티 | /tester UI 재설계 후 retention | 30일 retention < 20% |
| H5 진입점 | L1 GitHub App MVP | L1→L2 전환율 < 3% |
| H6 규제 | 법률 자문 (k-anonymity, provenance) | 검토 불가 판정 |

검증 우선순위: **H1 → H6 → H2 → H4 → H3 → H5**

---

## 12. 의도적으로 하지 않을 것

- ❌ Mabl/Testim/QA Wolf와 정면 경쟁
- ❌ 페르소나 벡터 DB (파일 + Memory Stream으로 충분)
- ❌ Git을 시스템 컴포넌트로 사용
- ❌ 별도 reflection scheduler (token budget이 자연 트리거)
- ❌ Meta-Agent 자동 적용 (Review Agent의 제안은 항상 Freddie 승인)
- ❌ 별도 ML experiment tracker (events log + manifest로 충분)
- ❌ "synthetic reviews" 워딩 (FTC 위반)
- ❌ 페르소나 개별 정확도 주장 (cohort 단위로만)
- ❌ 팀 규모 Permission system (1인 운영은 디렉토리 분리로 충분)

---

## 13. 외부 의존성

**유일한 외부 의존**: Stagehand (브라우저), Anthropic API (Claude), SAS 온체인.

**패턴 차용, 코드 차용 X**: OpenHarness, nanobot, Letta, Mem0, Zep — 검증된 패턴(hooks, frontmatter, tool registry, token budgeting, append-only memory)을 자체 구현.

**예외 조건**: M6 Review Agent가 H1 통과 후 자동화 loop로 확장될 때, OpenHarness 기반 구현을 우선 검토한다 (ADR 005 수정).

---

## 14. Open Questions

v4.1 기준으로 미해결, H1 진행 중 결정할 것들:

1. Token budget 임계값 — Sprint 실측 후 결정
2. Golden session 정의 방식 — 초기 5~10개 수동
3. Cache TTL 기본값 — 측정 후 조정
4. Cross-vendor 독립성 샘플링 주기 — H2 단계에서 결정
5. Advisor `max_uses` 값의 데이터 기반 재조정 — Sprint 1~2 텔레메트리 후
6. 첫 등대 고객 지역 — 한국 vs 북미

---

## Appendix A — Architectural Decisions Log

| ADR | 결정 | 근거 |
|---|---|---|
| 001 | 페르소나 = Memory Stream + Reflection (벡터 X) | Park 2023 ablation |
| 002 | Stable Core / Hot Zone 분리 | 가설 실험의 유연성 |
| 003 | 파일 기반 버전 관리 (Git X) | 단순성, GDPR 안전성 |
| 004 | Review Agent를 수동 도구로 시작, 자동화는 v4-full | H1 단계 자동화 불필요, 수동 개선 도구가 실제 병목 |
| 005 | 패턴만 차용하되, M6 자동화 확장 시 OpenHarness 우선 검토 | 통제 가능성 + 바퀴 재발명 회피의 균형 |
| 006 | 별도 reflection scheduler 없음 | Token budget overflow가 자연 트리거 |
| 007 | Events log 단일 진실의 원천 | 통합 분석 지점 |
| 008 | 콘텐츠 해시 ID 통일 | 무결성 + 재현성 + 캐시 키 |
| 009 | `persona_at()` 시간 함수 | H3 검증 핵심 |
| 010 | Multi-provider LLM 라우팅 | H2 multi-model 실험 |
| 011 | Anthropic Advisor tool 패턴 채택 | Executor+Advisor로 비용/정확도 최적화 |
| 012 | Constitution / Slice 분리 채택 | 큰 그림 + 좁은 구현 scope 양립 |
| 013 | 1인 운영 단계에서 Permission system 보류 | 디렉토리 분리 + 승인 CLI로 충분 |
| 014 | 3-Tier 모델 라우팅 (HIGH/MID/LOW) | 역할별 비용 최적화, tier→role config 매핑 |
| 015 | Plan/State/Tool 캐시 (콘텐츠 해시 키) | 중복 실행 제거, H2/H3 측정 시 OFF 모드 필수 |
| 016 | M3 내부에 Plan 단계 통합 | 멀티스텝 태스크 필수, 페르소나 차별성의 표현처 |
| 017 | Review Agent ↔ Version Manager 쌍으로 개선 루프 완성 | 제안과 적용의 물리적 분리로 안전성 확보 |

---

## Appendix B — Revision Policy

본 Constitution은 다음 시점에만 수정한다:

- Sprint 1 종료 다음날
- Sprint 2 종료 다음날
- H1 검증 완료 후 v4-full 진입 시 (대규모 revision 허용)

그 외 시점에 변경 필요사항이 발견되면 `experiments/constitution_notes/`에 메모만 추가하고 revision window까지 대기.

---

*이 Constitution은 v4 원본 + v4.1 advisor 패치 + 2026-04-12 대화 중 확정된 결정(3-Tier 라우팅, Cache, Plan 통합, Review Agent 명명, Version Manager 최소 구현)을 통합한 결과이다. 짝 문서 `Slice-H1.md`가 본 선언에 근거하여 실제 구현 범위를 지정한다.*
