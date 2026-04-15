# Evolution Harness — 지속 발전을 위한 뼈대

> 버전: 0.2.1 (PR-9 반영)
> 일자: 2026-04-15

시스템이 **데이터로부터 자기 자신을 개선**하려면 다음 5요소가 있어야 한다.
하나라도 빠지면 그 요소는 "정적"이 되고, 다른 팀원이 수동으로 돌봐야 한다.

```
┌──────────────────────────────────────────────────────────────────┐
│  Harness 5요소                                                   │
├──────────────────────────────────────────────────────────────────┤
│  1. 데이터 수집  — 매 결정 지점의 input/output 영구 기록         │
│  2. 평가 지표    — "이 변경이 나아졌는가?"를 판단할 rubric       │
│  3. 자동 합성    — 누적 데이터 → 개선안 제안 (LLM 또는 규칙)     │
│  4. 승인 게이트  — 사람/규칙/회귀 테스트가 승격 결정             │
│  5. 롤백 경로    — 새 버전이 더 나쁘면 이전 버전으로 즉시 복귀   │
└──────────────────────────────────────────────────────────────────┘
```

## 1. 현재 진화 가능 요소 전수 조사

persona_agent의 각 서브시스템이 **데이터로 진화할 수 있느냐**의 관점에서
전수 조사한 표. 진화 Loop이 **완성** / **부분** / **미구현**으로 분류.

| # | 요소 | 저장소 | 수집 | 지표 | 합성 | 게이트 | 롤백 | 상태 |
|---|---|---|:-:|:-:|:-:|:-:|:-:|---|
| 1 | **Session observations** (L1) | `personas/<id>/history/` | ✅ | — | — | — | — | **완성** (passive memory) |
| 2 | **Persona reflections** (L2) | `personas/<id>/reflections/` | ✅ | 🟡 | ✅ **PR-9** | 🟡 | ✅ immutable | **완성** (PR-9 자동 합성) |
| 3 | **Soul revision** (L3) | `soul/vNNN.md` + manifest | ✅ | 🟡 (drift 감지) | ❌ | ❌ | ✅ version_manager | **부분** (trigger 있지만 pipeline 없음) |
| 4 | **Selector memory** | `cache/selector_memory/` | ✅ | ✅ (성공률) | ✅ (get_failed_strategies) | ✅ | ❌ | **완성** (성공 전략 재시도 + 실패 회피) |
| 5 | **Prompt versioning** | `prompts/*/vNNN.md` + manifest | ✅ | 🟡 (golden session) | 🟡 (review_agent.propose) | ❌ **수동** | ✅ rollback() | **부분** |
| 6 | **Plan cache** | `cache/plan_cache/` | ✅ | — | — | — | TTL | **정적** (hit-or-miss) |
| 7 | **Trait mapping 규칙** (TesterProfile → 5축) | `adapters/tester_to_soul.py` 하드코딩 | ❌ | ❌ | ❌ | ❌ | ❌ | **정적** — 가장 큰 구멍 |
| 8 | **External benchmarks** (GA4, Open Bandit) | `experiments/datasets/` | ❌ (정적 CSV) | ❌ | ❌ | ❌ | ❌ | **정적** (분기당 1회 수동) |
| 9 | **Failure taxonomy** (F001, F002…) | `_shared/playbook_failure_modes.md` | ❌ | ❌ | ❌ | ❌ | ❌ | **정적** |
| 10 | **Reward / quality scoring** (41rpm) | `llm.ts:calculateQualityScore` | ❌ | ❌ | ❌ | ❌ | ❌ | **정적** (power curve 고정) |
| 11 | **LLM routing** (tier per role) | `config/llm_routing/routing.yaml` | 🟡 events_log | ❌ (비용/정확도 없음) | ❌ | ❌ | ✅ yaml revert | **정적** |
| 12 | **Cohort generation 규칙** (persona_generator LHS) | `persona_generator.py` | ❌ | ❌ | ❌ | ❌ | ❌ | **정적** |
| 13 | **Hallucination audit rules** | `hallucination_guard.py` 하드코딩 | ✅ findings log | 🟡 (false positive rate 미집계) | ❌ | ❌ | ❌ | **부분** |
| 14 | **Provenance chain** | `cache/provenance_chain.jsonl` | ✅ HMAC append | ✅ verify_chain | — | — | ❌ (audit만) | **완성** (audit-only) |
| 15 | **Metrics / events** | `events/events.jsonl` | ✅ | 🟡 metrics.summary | ❌ | ❌ | ❌ | **부분** (대시보드 없음) |

**범례**: ✅ 구현 / 🟡 부분 / ❌ 없음

---

## 2. 진화 계층 (persona 관련)

### L1 — Session Memory (✅ 완성)
- 매 턴 `append_observation`이 immutable JSON 저장
- 다음 세션의 `read_persona`가 자동으로 merge → plan 프롬프트 주입
- **비용**: 0 (파일 I/O만)
- **검증**: 방금 naver.com 세션에서 +4 observations 확인

### L2 — Persona Reflection (✅ **이번 PR-9**)
- `post_session_end` hook이 `reflection_engine.maybe_synthesize` 자동 호출
- pending obs ≥ 10이면 level1_pattern 프롬프트로 Sonnet 1회 호출
- 결과: `r_xxx.json` append + `soul_drift` 메타 캡처
- **비용**: ~$0.02/synthesis, 평균 10 세션당 1회
- **검증**: 7 단위 테스트 통과 (threshold/dedup/malformed/flag/drift/fenced JSON)

### L3 — Soul Revision (❌ 미구현)
**트리거 조건 제안**:
- 누적 level1 reflection 중 `meta.soul_drift_detected=true`가 연속 3건 이상
- OR 마지막 soul version 이후 level1 reflection이 20개 누적

**합성 파이프라인 제안**:
```python
def maybe_revise_soul(persona_id):
    state = read_persona(persona_id)
    drift_refs = [r for r in state.reflections if _has_drift(r)]
    if len(drift_refs) < 3:
        return None
    # Call LLM with: current soul + drift reflections + observation sample
    new_soul_text = llm_call(role="soul_revision", system=load_prompt("persona/soul_revision"), ...)
    # Validate: YAML parses, all 5 traits present, trait values in [0,1]
    validate_soul_schema(new_soul_text)
    # Append new version via version_manager
    return version_manager.save_version(f"personas/{persona_id}/soul", new_soul_text,
                                        author="reflection_engine", message="auto-drift-revision")
```

**승인 게이트 제안** (H2 범위):
- A/B 평가: 구 soul로 5 세션, 신 soul로 5 세션, 페르소나 일관성 + action 품질 비교
- pass → manifest.current 업데이트
- fail → 신 버전은 파일로 남되 current 변경 없음 (수동 검토)

### L4 — Trait Rule Meta-Learning (❌ 미구현, 가장 큰 레버리지)

1000명 페르소나 × 50 세션 = 50k 관측에서:
```
각 페르소나 p에 대해:
  trait_predicted = adapters.tester_to_soul(p.profile)   # 초기 규칙
  trait_observed  = aggregate_from_observations(p)       # 실측
  drift[axis] = trait_observed - trait_predicted
집계:
  for each TesterProfile 필드 조합 (예: primary_device=mobile):
    mean_drift = mean over personas with 그 조합
```

→ **trait mapping YAML의 규칙값을 학습된 값으로 자동 업데이트**
→ 새 테스터가 등록하면 더 정확한 초기 soul로 시작

**구현 비용**: 주 1회 배치 파이프라인, ~$10/주, 2주 작업.

---

## 3. 진화 가능하지만 안 되고 있는 6개 (우선순위)

현재 정적이거나 부분만 있는 요소 중, ROI가 높은 순서로 제안.

### 🥇 **Selector Memory 승격 정책** (부분 → 완성)
selector_memory는 성공/실패를 이미 기록하지만, **승격 정책이 없어서 오래된 실패 패턴이 영원히 살아남음**.
- Add: `prune_stale(site, older_than_days=30)` — 30일 지난 실패 레코드 제거
- Add: 성공률 `success_rate = success_count / (success + failure)`, 낮으면 strategy 자체 폐기
- 난이도: 반나절 / 비용: 0
- 효과: 셀렉터 히트율 향상 → 세션 성공률 ↑

### 🥈 **Prompt Versioning 자동 승격** (부분 → 완성)
`review_agent.propose()`가 이미 수정안 draft를 생성하지만 **승인 게이트가 수동**.
- Add: golden session 회귀 테스트 자동 실행 (기존 `golden_sessions/` dir 활용)
- Add: 새 프롬프트로 5 세션 → 평가 점수 비교 → 유의하게 좋으면 `manifest.current` 승격
- 난이도: 2~3일 / 비용: golden session 돌 때마다 ~$0.5
- 효과: 프롬프트가 실제 데이터로 자가 개선

### 🥉 **Trait Mapping YAML화** (정적 → 부분)
`adapters/tester_to_soul.py`의 if/else를 `data/config/trait_mapping.yaml`로 externalize.
- 동작 변화 없이 설정만 분리 (backward-compatible)
- 핫 리로드 지원 (configure() 재호출)
- 난이도: 반나절 / 비용: 0
- 효과: 코드 배포 없이 튜닝 가능 → L4 meta-learning의 전제

### 4️⃣ **LLM Routing 비용/정확도 피드백** (정적 → 부분)
events_log에 이미 토큰 수 기록됨. 추가로:
- role별 평균 비용 + outcome success rate 집계
- `mid` → `low`로 다운그레이드해도 outcome 변화 없는 role 자동 식별
- 난이도: 1일 / 비용: 0
- 효과: 세션당 비용 30~50% 절감 여지

### 5️⃣ **Failure Taxonomy 자동 발견** (정적 → 부분)
현재 F001~F005 같은 failure code는 playbook에 하드코딩. 실제 실패들을 클러스터링해서 신규 유형 발견 가능.
- 난이도: 2일 / 비용: ~$1/주 (embedding + clustering)
- 효과: 새 실패 패턴을 빠르게 포착 → 복구 전략 추가

### 6️⃣ **External Benchmark 자동 갱신** (정적)
GA4 sample / Open Bandit은 분기 업데이트. 새 공개 데이터셋 감지해서 자동 편입.
- 난이도: 1주 / 비용: 파이프라인 구축
- 효과: reality check의 최신성 보장

---

## 4. Harness 5요소 체크리스트 (신규 기능 추가 시)

새 진화 가능 요소를 도입할 때 반드시 다음을 설계해야 한다.

### ① 데이터 수집 — "어디에 쌓이는가?"
- [ ] Append-only 저장소 (파일 / DB / events.jsonl)
- [ ] 각 레코드에 timestamp + source (어떤 세션/페르소나가 생성했는가)
- [ ] 용량 증가 전략 (영구 / TTL / 압축 / cold storage)

### ② 평가 지표 — "나아진 걸 어떻게 아는가?"
- [ ] Primary metric (예: session success rate, token cost, action latency)
- [ ] Secondary / guardrail (회귀 방지: 이건 떨어지면 안 됨)
- [ ] Minimum sample size (통계적으로 유의미한 비교 최소 n)

### ③ 자동 합성 — "어떻게 개선안을 만드는가?"
- [ ] 트리거 (시간 기반 / 임계치 기반 / 수동)
- [ ] 합성 로직 (규칙 / LLM / ML)
- [ ] 비용 상한 (합성 1회당 최대 $ / 월 예산)
- [ ] Best-effort 실패 처리 (합성 실패해도 시스템 계속 작동)

### ④ 승인 게이트 — "무엇이 승격 결정하나?"
- [ ] 자동 게이트 (회귀 테스트 / 지표 비교)
- [ ] 수동 게이트 (approval flow, 누가 볼 건가)
- [ ] 점진 롤아웃 (feature flag / 비율 제한)

### ⑤ 롤백 — "나쁘면 어떻게 되돌리나?"
- [ ] 새 버전과 이전 버전이 동시에 존재하는가 (versioning)
- [ ] 단일 명령으로 이전 상태 복구 가능한가
- [ ] 롤백 후 데이터 무결성 (진행 중 세션 처리)

---

## 5. 41rpm 맥락 — 왜 harness가 중요한가

41rpm이 H1 "세그먼트 분기 진단" 단계를 넘어 H2 "반복 테스트 시장"으로 가려면:

| 사용량 | 요구되는 진화 요소 |
|---|---|
| 테스터 10명 × 3회 | L1 (memory) — 이미 동작 |
| 테스터 100명 × 10회 | L2 (reflection) — **이번 PR-9로 준비** |
| 테스터 1000명 × 50회 | L3 (soul revision) + L4 (trait meta-learning) — 다음 분기 |
| 테스터 10000명 × 100회 | Failure taxonomy 자동 발견 + benchmark 자동 갱신 |

**각 단계는 `사용량이 쌓이는 즉시 자동화된 다음 레이어를 열어야 한다`**. 사람이 수동으로 튜닝하는 한, 41rpm의 플라이휠은 돌지 않는다.

Solana SAS 연결 지점:
- 페르소나가 L2 reflection을 5개 이상 누적 → "matured persona" 속성 발행
- L3 soul revision 1회 통과 → "validated persona" 속성 발행
- 이 속성이 테스트 할당 우선순위 / 보상 증폭에 사용

---

## 6. 즉시 실행 가능한 다음 작업 (ROI 순)

1. **PR-10 — Selector Memory Pruning** (반나절, 비용 0)
2. **PR-11 — Trait Mapping YAML** (반나절, 비용 0, L4 전제)
3. **PR-12 — Soul Revision (L3) 트리거 + 검증** (3일, $20/월)
4. **PR-13 — Prompt 자동 승격 + Golden Session 회귀** (3일, $50/월)
5. **PR-14 — Events Log 대시보드 + LLM 비용 피드백** (2일)
6. **PR-15 — Trait Meta-Learning 배치** (2주, $10/주)

각 PR은 "데이터로 자기 개선" 하는 피드백 루프를 **하나씩** 닫는다. H2 시장 진입 전에 최소 PR-10~PR-13까지는 완료되어야 스케일 가능.

---

## 7. 참고

- PR-9 구현: `persona_agent/src/persona_agent/_internal/persona/reflection_engine.py`
- 테스트: `persona_agent/tests/test_reflection_engine.py` (7건)
- Soul drift 프롬프트: `data/prompts/reflection/level1_pattern/v001.md`
- Hook 배선: `_internal/core/hooks.py:post_session_end`
- 아키텍처 전체: `ARCHITECTURE.md`
