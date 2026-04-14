# 41R Slice-H1 — 현재 구현 범위

> **작성일**: 2026-04-12
> **대응 문서**: `41R-Constitution.md` v1.0
> **목표**: H1 (바이어 검증) 가설 검증을 위한 최소 제품
> **데드라인**: 5월 첫째 주 CPO 콜드 아웃바운드 시작

---

## 0. 범위 선언

본 Slice는 Constitution에 선언된 전체 구조 중 **H1 검증에 필요한 부분만** 실제 구현한다. 나머지는 stub으로 자리를 잡아두되 `NotImplementedError`로 명시적으로 비워둔다.

**충동 관리 원칙**: stub을 채우고 싶을 때 `experiments/backlog.md`에 메모만 하고 넘긴다. H1 검증 종료 전까지 v4-full 영역 작업 금지.

---

## 1. 구현 / Stub 상태

### 모듈

| 모듈 | 상태 | 비고 |
|---|---|---|
| M1 Persona Store | **구현** | 파일 I/O + 시간 함수 기본형 |
| M2 Browser Runner | **구현** | Stagehand 기존 코드 활용 |
| M3 Agent Loop | **구현** | Plan + Loop 통합 |
| M5 Report Generator | **구현** | PDF + lineage.json |
| M6 Review Agent | **구현** | CLI 도구, 수동 트리거 |
| M7 Version Manager | **구현 (최소)** | 4개 함수만 |
| M4 Provenance | stub | `NotImplementedError` |

### Cross-cutting

| 컴포넌트 | 상태 | 비고 |
|---|---|---|
| Provider Router | **구현** | 3-Tier + Advisor |
| Cache | **구현** | Plan/Page/Tool 3종 |
| Events Log | **구현** | JSONL append |
| Hooks | **최소 구현** | `post_session_end` 하나 |
| Token Budgeter | stub | 초기엔 수동 관리 |
| Tool Registry | stub | |
| Permission System | 삭제 | 1인 운영, 디렉토리 분리로 대체 |

---

## 2. 작업 순서

```
토요일 오전   Constitution.md 확정 + Slice-H1.md (현재 문서) 완성
토요일 오후   디렉토리 생성 + 모든 stub 파일 + Hot Zone manifest
             Provider Router (3-Tier config 포함)
             Events Log 기반 구조

일요일 오전   M1 Persona Store 구현
             ★ observation 필드 완전성 검증
일요일 오후   M7 Version Manager 구현 (M6가 의존하므로 먼저)

월요일       M2 Browser Runner (Stagehand 어댑터)
             Cache 레이어 기본
화요일       M3 Agent Loop — Plan 단계
수요일       M3 Agent Loop — Decision/Tool 단계 + 통합 테스트
목요일       M5 Report Generator + lineage
금요일       M6 Review Agent (CLI)
             첫 end-to-end 세션 실행

다음주 초    Golden session 5개 수동 정의
             공개 A/B 역검증 케이스 3건 실행
             Sample report 완성
다음주 후반  CPO 콜드 아웃바운드 시작
```

---

## 3. M1 Persona Store — 구현 명세

```python
# modules/persona_store.py

def create_persona(persona_id: str, soul_text: str) -> None: ...
def read_persona(persona_id: str, at_time: datetime = None) -> PersonaState: ...
def append_observation(persona_id: str, obs: dict) -> str: ...
def append_reflection(persona_id: str, level: int, text: str, sources: list) -> str: ...
def persona_at(persona_id: str, timestamp: datetime) -> PersonaSnapshot: ...
def list_personas() -> list[str]: ...
```

**Observation 필수 필드 (모두 필수, 빠뜨리면 에러)**:
- `obs_id` (콘텐츠 해시)
- `timestamp` (UTC ms)
- `persona_id`
- `persona_version`
- `content`

`persona_at()`은 H1에선 단순 구현도 OK: 해당 시점까지의 history + 활성 reflection 합쳐서 반환. 최적화는 v4-full.

---

## 4. M3 Agent Loop — 구현 명세

```python
def run_session(persona_id, url, task) -> SessionLog:
    persona = M1.read_persona(persona_id)
    
    # Plan 단계 (1회, 캐시 조회 우선)
    plan = plan_cache.get_or_generate(persona, task, url)
    
    session = M2.start_session(url, persona)
    turn = 0
    
    while not done and turn < MAX_TURNS:
        raw_state = M2.get_state(session)
        state = page_summarizer(raw_state)              # [LOW] + cache
        
        decision = decision_judge(persona, plan, state)  # [MID + advisor]
        tool = tool_selector(decision)                   # [LOW] + cache
        
        result = M2.run_action(session, tool)
        
        obs = build_observation(persona, state, decision, result)
        M1.append_observation(persona_id, obs)
        events_log.append(decision, advisor_invoked=...)
        
        if decision.plan_deviation:
            plan = replan(persona, plan, recent_obs)
        
        done = decision.done
        turn += 1
    
    return M2.end_session(session)
```

**Hot Zone 프롬프트 초판 작성**:
- `prompts/agent/plan_generator/v001.md`
- `prompts/agent/decision_judge/v001.md`
- `prompts/agent/tool_selector/v001.md`
- `prompts/agent/page_summarizer/v001.md`
- `prompts/agent/replan_trigger/v001.md`

각 프롬프트는 frontmatter 포함, manifest.yaml로 v001을 current로 지정.

---

## 5. H1 검증 체크리스트

- [ ] Golden session 5~10개 정의 (쇼핑몰/SaaS 전형)
- [ ] 공개 A/B 테스트 케이스 3건 선정 및 역검증 실행
- [ ] Sample report 1부 완성 (A/B 비교 포함)
- [ ] lineage.json이 재현 가능하게 채워짐 확인
- [ ] CPO 30명 리스트업
- [ ] 콜드 아웃바운드 메시지 템플릿 작성
- [ ] 피드백 수집 폼 준비

---

## 6. 안전장치

**데드라인**: 5월 첫째 주까지 콜드 아웃바운드 시작 못 하면 → **코드 품질과 무관하게 수동 리포트로 H1 진행**. 페르소나 수동 기술, 브라우저 스크린 레코딩, 리포트 수작업 조립. H1은 바이어가 돈을 낼지 검증하는 가설이지 시스템 품질 가설이 아니다.

**Kill**: 유료 전환율 5% 미만이면 H2 이하 전체 중단.

**분리**: Review Agent는 `proposals/`에만, Version Manager만 `prompts/`에. 이 경계는 코드 수준에서 강제.

**Constitution 고정**: Sprint 1/2 종료 시점에만 revision. 그 외엔 `experiments/constitution_notes/`에 메모.

---

## 7. v4-full 백로그 (나중)

- M4 Provenance 완전 구현 (SAS 온체인)
- M7 Version Manager 확장 (snapshot/restore)
- Token Budgeter
- Tool Registry
- Hook system 풀버전
- Reflection 자동화 (token overflow 트리거)
- Review Agent 자동화 루프 (OpenHarness 기반 검토)
- Multi-model 비교 실험 인프라
- Permission system (팀 확장 시)

---

*본 Slice는 Constitution v1.0의 선언 위에서 H1 검증까지의 최소 경로만 지정한다. H1 통과 후 v4-full 진입 시 Constitution revision과 함께 Slice-H2 작성.*
