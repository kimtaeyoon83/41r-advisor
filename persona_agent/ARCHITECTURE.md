# persona_agent — 아키텍처 · 사용법 · 인터페이스

> 버전: 0.2.0.dev0
> 문서 일자: 2026-04-15
> 소스 홈: `/home/kimtayoon/myrepo/41r-advisor/persona_agent/`

---

## 1. 한 줄 요약

**캘리브레이션된 페르소나가 실제 브라우저로 제품을 써보고, 세그먼트별 반응 차이를 24시간·건당 ~$5에 진단하는 재사용 가능한 파이썬 패키지.**

---

## 2. 설계 원칙 (3)

### 2.1 단일 파사드 + `lowlevel` 네임스페이스
바깥 서비스는 `persona_agent`(고수준) 또는 `persona_agent.lowlevel`(파워유저) 두 표면만 안다. 내부 구조(`_internal/`)는 언제든 재배치 가능.

### 2.2 Workspace 주입
모든 쓰기 경로는 `Workspace(root=...)`에서 나온다. 숨겨진 CWD 의존 없음 → 멀티테넌트 SaaS가 테넌트당 workspace를 가질 수 있다.

### 2.3 Overlay 저장소 (built-in vs workspace)
**읽기는 두 소스 머지**: `workspace.personas_dir` + `workspace.builtin_personas_dir`.
**쓰기는 항상 workspace.personas_dir**. 덕분에:
- wheel에 번들된 built-in 페르소나(`p_impulsive` 등)는 read-only 보호
- 각 세션의 observation/reflection은 workspace에 누적되어 **진화 지속**
- 같은 built-in을 여러 테넌트가 공유, 각자 다른 진화 경로

---

## 3. 설치

### 3.1 개발 모드 (이 리포 내부)
```bash
cd /home/kimtayoon/myrepo/41r-advisor/41r
source .venv/bin/activate
pip install -e ../persona_agent
```

### 3.2 Wheel 배포
```bash
cd persona_agent
python -m build --wheel
# dist/persona_agent-0.2.0.dev0-py3-none-any.whl

# 소비자 측
pip install persona_agent-0.2.0.dev0-py3-none-any.whl
pip install "persona_agent[browser,analysis,benchmark]"  # optional extras
```

### 3.3 Optional Extras

| Extra | 포함 | 필요 시점 |
|---|---|---|
| `browser` | `playwright>=1.49` | browser 모드 `run_session`/`run_cohort(mode="browser")` |
| `reports` | `weasyprint>=62` | PDF 리포트 (기본 HTML은 불필요) |
| `analysis` | `numpy>=1.26, scipy>=1.11` | CATE, bootstrap CI, p-value 재계산 |
| `benchmark` | `pandas>=2.0` | GA4/Open Bandit 베이스라인 로드 |
| `all` | 위 전부 | 풀 기능 |
| `dev` | pytest, ruff | 개발·테스트 |

base 의존성: `anthropic>=0.52`, `pyyaml>=6.0`, `jinja2>=3.1`.

---

## 4. Quick Start

### 4.1 최소 예제 (text 모드, 5 페르소나, ~$0.10)
```python
import persona_agent as pa
from persona_agent.lowlevel import run_cohort, generate_cohort_report

# 워크스페이스 주입 (개발 중엔 CWD=41r/에서 자동 추론도 가능)
pa.configure(pa.Workspace(
    root=Path("/var/persona_jobs/job_123"),
    personas_dir=Path("/var/persona_jobs/job_123/personas"),
    builtin_personas_dir=None,  # 번들 데이터 자동 (PR-9 예정, 지금은 명시)
    prompts_dir=...,             # 보통 번들 데이터
    config_dir=...,
    reports_dir=Path("/var/persona_jobs/job_123/reports"),
))

# 분석 실행
result = run_cohort(
    cohort_run_id="cohort_manual5",
    url="https://slack.com/pricing",
    task="20-50명 SaaS 스타트업 협업툴 선택",
    mode="text",             # "browser"도 가능 (느림·고가)
    max_workers=5,
)

# HTML 리포트
report_id = generate_cohort_report(result["output_path"])
# reports/cohort_rpt_<id>/cohort_report.html
```

### 4.2 Browser 모드 단일 세션 (~$0.20~0.50, 2~5분)
```python
from persona_agent.lowlevel import run_session

log = run_session(
    persona_id="p_pragmatic",
    url="https://www.naver.com/",
    task="오늘 IT 뉴스 헤드라인 1개 확인",
)
print(log.outcome, log.total_turns)
# task_complete 4

# 세션 중 각 턴의 observation이 자동으로
# workspace/personas/p_pragmatic/history/o_xxx.json 에 append됨 → 진화
```

### 4.3 환경변수 + 번들 YAML로 Settings 빌드
```python
from persona_agent.settings import load_settings
from pathlib import Path

settings = load_settings(
    workspace_dir=Path("/var/persona_jobs/job_123"),
    overrides={"vision_mode": False, "max_concurrent_sessions": 8},
)
# ANTHROPIC_API_KEY env 필수, 없으면 ConfigurationError
```

---

## 5. 패키지 레이아웃

```
persona_agent/
├── pyproject.toml                  hatchling, extras, 패키지 데이터
├── conftest.py                     테스트용 자동 workspace
├── ARCHITECTURE.md                 (이 문서)
├── README.md
└── src/persona_agent/
    ├── __init__.py                 파사드 (lazy lowlevel via __getattr__)
    ├── lowlevel.py                 31개 함수 re-export
    ├── settings.py                 Settings + load_settings
    ├── workspace.py                Workspace/configure/get_workspace re-export
    ├── errors.py                   15개 예외 계층
    ├── _internal/                  (사적, 재배치 가능)
    │   ├── core/                   provider_router, cache, events_log, metrics, hooks, workspace
    │   ├── session/                agent_loop, browser_runner, vision_clicker, selector_memory, plan_cache
    │   ├── persona/                persona_store, persona_generator
    │   ├── cohort/                 cohort_runner, cohort_report
    │   ├── integrity/              hallucination_guard, claim_tagger, provenance
    │   ├── analysis/               cate_validator, cross_cohort_meta, benchmark_loader
    │   └── reports/                prompt_loader, version_manager, review_agent, report_gen, report_analyzer
    └── data/                       wheel에 번들
        ├── prompts/                (6 manifest 그룹)
        ├── config/                 (llm_routing, cache, reflection_triggers)
        └── personas/               (p_impulsive, p_cautious 등 10개)
```

---

## 6. 6그룹 모듈 맵

| 그룹 | 파일 | 책임 |
|---|---|---|
| **core** | provider_router.py | 3-tier LLM 라우팅 (Haiku/Sonnet/Opus), Anthropic client 관리 |
| | cache.py | content-hash 범용 캐시 (plan/page/tool_selection) |
| | events_log.py | JSONL append-only 이벤트 로그 |
| | workspace.py | Workspace dataclass + configure/get_workspace |
| | metrics.py | 세션 메트릭 집계 + dashboard.json |
| | hooks.py | post_session_end / post_cohort_complete |
| **session** | agent_loop.py | 1 페르소나 × 1 URL × 1 task 메인 루프 (MAX_TURNS=10) |
| | browser_runner.py | Playwright 조작 + 9 원시 액션 dispatch |
| | vision_clicker.py | 스크린샷 좌표 기반 click/fill (셀렉터 실패 fallback) |
| | selector_memory.py | 사이트별 셀렉터 성공/실패 기록·학습 |
| | plan_cache.py | plan 프롬프트 결과 캐시 |
| **persona** | persona_store.py | create/read/append_observation/append_reflection (overlay 지원) |
| | persona_generator.py | LHS 샘플링으로 N명 자동 생성 (CohortSpec → run_id) |
| **cohort** | cohort_runner.py | multiprocessing.Pool로 N 페르소나 병렬 실행 |
| | cohort_report.py | Wilson CI + trait×outcome 상관 + HTML 생성 |
| **integrity** | hallucination_guard.py | 리포트 숫자 · p-value · claim 태그 검증 |
| | claim_tagger.py | 자동 `data-src="file.json:field"` 태깅 |
| | provenance.py | HMAC-SHA256 체인 (tamper-evident audit log) |
| **analysis** | cate_validator.py | 개인화 효과 추정 + bootstrap CI |
| | cross_cohort_meta.py | 사이트 간 trait 상관 일관성 |
| | benchmark_loader.py | GA4/Open Bandit 실제 수치 로드 + reality check |
| **reports** | prompt_loader.py | Hot Zone 프롬프트 로드 + `_shared` 참조 자동 주입 |
| | version_manager.py | append-only 버전 관리 + manifest (v001→v002) |
| | report_gen.py | 세션 로그 → 비즈니스 인사이트 HTML |
| | report_analyzer.py | LLM 분석 레이어 (세션 로그 → 인사이트 추출) |
| | review_agent.py | session inspect / evaluate / propose / compare |

---

## 7. 공개 API

### 7.1 파사드 (`persona_agent/__init__.py`)

```python
# 설정
persona_agent.Settings            # dataclass
persona_agent.Workspace           # dataclass
persona_agent.configure(ws)
persona_agent.get_workspace()     # -> Workspace

# 조회 (lazy, __getattr__로 필요 시 lowlevel 로드)
persona_agent.list_personas()     # -> list[str]

# 네임스페이스
persona_agent.lowlevel            # 모듈 (31 함수)

# 버전
persona_agent.__version__         # "0.2.0.dev0"
```

### 7.2 예외 (15개)

```python
persona_agent.PersonaAgentError         # 루트
├── ConfigurationError                  # Settings/Workspace 오류
├── MissingExtraError                   # optional extra 미설치 (.extra, .install_hint)
├── SessionError                        # 단일 세션 실패
│   ├── BrowserError                    # Playwright 오류
│   ├── VisionError                     # Vision 좌표 실패
│   ├── PlanError                       # plan 재시도 한계
│   └── LLMError                        # provider 오류 / 예산 초과
├── CohortError                         # 다중 세션 실패 (.partial_result)
├── GuardrailError
│   ├── HallucinationFoundError         # audit 위반
│   └── UntaggedClaimError
├── ProvenanceError                     # HMAC 체인 깨짐 (.broken_at_index)
└── PersonaError
    ├── PersonaNotFoundError
    └── PersonaExistsError
```

### 7.3 lowlevel (`persona_agent.lowlevel`, 31 함수)

```python
# --- 세션 ---
run_session(persona_id, url, task) -> SessionLog

# --- 코호트 ---
run_cohort(cohort_run_id, url, task, mode="text", max_workers=5) -> dict
aggregate_cohort(cohort_result) -> dict
render_cohort_html(cohort_result, aggregation) -> (report_id, report_dir)
generate_cohort_report(cohort_result_path) -> report_id

# --- 페르소나 ---
create_persona(persona_id, soul_text) -> None
read_persona(persona_id, at_time=None) -> PersonaState
list_personas() -> list[str]
append_observation(persona_id, obs) -> obs_id
append_reflection(persona_id, level, text, sources) -> ref_id
persona_at(persona_id, timestamp) -> PersonaSnapshot
CohortSpec(segment_name, size, age_range, ...)  # dataclass
generate_cohort(spec: CohortSpec) -> run_id

# --- 무결성 ---
audit_report(report_path, ground_truth_dirs) -> list[Finding]
audit_numbers(report_path, ground_truth_dirs) -> list[Finding]
audit_pvalues(report_path, recompute_targets) -> list[Finding]
audit_tagged_claims(report_path) -> list[Finding]
generate_audit_trail(report_path, output_path) -> None
suggest_tags(report_path, gt_dirs) -> list[Suggestion]
apply_tags(report_path, suggestions) -> None
claim_coverage_report(report_path, gt_dirs) -> dict
record_provenance(data: dict) -> entry_id
verify_chain() -> (ok: bool, broken_at: int | None)

# --- 분석 ---
validate_predictions(ab_data, features, n_bootstrap) -> CATEResult
run_meta(cohort_pattern, min_n) -> dict
render_meta_markdown(meta) -> str
get_baseline() -> BaselineMetrics  # GA4 + Open Bandit
diagnose_cohort(aggregation, baseline) -> dict

# --- 리포트 ---
generate_report(session_logs, personas, comparison_mode="ab") -> report_id
inspect_session(session_id) -> dict
evaluate_session(session_id) -> dict
```

---

## 8. Workspace 계약

### 8.1 디렉토리 레이아웃
```
<workspace_dir>/
├── sessions/              agent_loop 세션 로그 (s_<id>.json)
├── cohort_results/        cohort_runner 결과 (cohort_<ts>_<hash>.json)
├── personas/              workspace-created 페르소나 (generated cohorts + custom)
│   └── p_XXX/
│       ├── soul/          v001.md + manifest.yaml (versioned)
│       ├── history/       o_XXX.json (immutable observations)
│       ├── reflections/   r_XXX.json (level1/2 합성, immutable)
│       └── snapshots/     (v4-full에서 활용)
├── reports/               생성된 HTML 리포트
├── cache/
│   ├── plan_cache/
│   ├── selector_memory/
│   └── content_cache/
└── events/
    └── events.jsonl
```

### 8.2 Built-in 페르소나 (read-only, wheel 내부)

```
persona_agent/data/personas/
├── p_impulsive/         충동적 28세 남 (impulsiveness=0.95, research=0.1)
├── p_cautious/          신중 35세 여 (research=0.95, privacy=0.8)
├── p_budget/            예산 32세 여 (price_sensitivity=0.95)
├── p_pragmatic/         실용 42세 남 (research=0.6, tech_lit=0.9)
├── p_senior/            시니어 58세 여 (impulsiveness=0.1, vision_dep=0.3)
├── p_b2b_buyer/
├── p_genz_mobile/
├── p_parent_family/
├── p_creator_freelancer/
└── p_overseas_kor/
```

### 8.3 Overlay 규칙

| 작업 | 동작 |
|---|---|
| `read_persona("p_impulsive")` | soul은 builtin에서, observations/reflections는 workspace에서 읽어 머지 |
| `append_observation("p_impulsive", obs)` | 항상 `workspace/personas/p_impulsive/history/`에 추가 |
| `create_persona("p_impulsive", ...)` | FileExistsError (builtin 충돌 방지) |
| `list_personas()` | workspace ∪ builtin (중복 제거) |
| `append_reflection("p_impulsive", ...)` | workspace에 추가 |

---

## 9. Settings 필드

| 필드 | 타입 | 기본값 | 출처 |
|---|---|---|---|
| `anthropic_api_key` | str | (필수) | `$ANTHROPIC_API_KEY` |
| `anthropic_base_url` | str∣None | None | `$ANTHROPIC_BASE_URL` |
| `workspace_dir` | Path | `./persona_workspace` | 생성자 인자 |
| `prompts_dir` | Path∣None | None (→번들) | 오버라이드 |
| `config_dir` | Path∣None | None (→번들) | 오버라이드 |
| `builtin_personas_dir` | Path∣None | None (→번들) | 오버라이드 |
| `vision_mode` | bool | True (H1) | 오버라이드 |
| `session_budget_usd` | float | 0.5 (H1) | 오버라이드 |
| `max_concurrent_sessions` | int | 4 | 오버라이드 |
| `log_events` | bool | True | 오버라이드 |
| `fail_fast` | bool | False | 오버라이드 |
| `llm_routing` | LLMRouting | (YAML 로드) | `data/config/llm_routing/routing.yaml` |
| `cache` | CacheConfig | enabled=True, ttl=86400 | `data/config/cache/cache_config.yaml` |
| `reflection_triggers` | ReflectionTriggers | (YAML 로드) | `data/config/reflection_triggers/triggers.yaml` |

---

## 10. 데이터 모델

### 10.1 PersonaState (read_persona 반환)
```python
@dataclass
class PersonaState:
    persona_id: str
    soul_version: str             # "v001", "v002", ...
    soul_text: str                # markdown (YAML frontmatter + 서술)
    observations: list[dict]      # 시간순, overlay-merged
    reflections: list[dict]       # level1/2 합성
```

### 10.2 PersonaSnapshot (persona_at 반환)
`PersonaState` + `timestamp` + `active_reflections`만 필터 (해당 시점 이전 + active).

### 10.3 CohortSpec (persona_generator 입력)
```python
@dataclass
class CohortSpec:
    segment_name: str                         # "20대 여성 직장인"
    size: int                                 # 20
    age_range: tuple[int, int]                # (22, 29)
    gender_dist: dict[str, float]             # {"F": 1.0}
    occupations: list[str]
    region: str                               # "KR-Seoul"
    # 5 성향 축: (mean, std), [0,1] 범위로 clip
    impulsiveness: tuple[float, float]
    research_depth: tuple[float, float]
    privacy_sensitivity: tuple[float, float]
    price_sensitivity: tuple[float, float]
    visual_dependency: tuple[float, float]
```

### 10.4 Observation (observation schema)
```json
{
  "persona_id": "p_pragmatic",
  "persona_version": "v001",
  "content": {"turn": 1, "page_state": "...", "action": "click", "reason": "..."},
  "timestamp": "2026-04-15T03:30:00+00:00",
  "obs_id": "o_91564488ca89f274"
}
```
`persona_id`, `persona_version`, `content` 필수. `obs_id`는 자동 (content hash).

### 10.5 SessionLog (run_session 반환)
```python
@dataclass
class SessionLog:
    session_id: str               # "s_b80b51a5"
    persona_id: str
    url: str
    task: str
    outcome: str                  # "task_complete" | "abandoned" | "partial"
    total_turns: int
    duration_sec: float
    turns: list[TurnRecord]
```

### 10.6 CohortResult (run_cohort 반환)
```python
{
    "cohort_run_id": "cohort_manual5",
    "url": "https://...",
    "task": "...",
    "mode": "text",
    "n_personas": 5,
    "n_completed": 3,
    "results": [
        {
            "persona_id": "p_pragmatic",
            "persona_age": 42,
            "persona_traits": {"impulsiveness": 0.5, ...},
            "outcome": "task_complete",
            "predicted_turns": 7,
            "drop_point": None,
            "key_behaviors": [...],
            "frustration_points": [...],
            "conversion_probability": 0.72,
            "reasoning": "...",
            "tokens": {"input_tokens": 1182, "output_tokens": 938},
        },
        ...
    ],
    "output_path": "/path/to/cohort_xxx.json",
}
```

---

## 11. 실행 흐름

### 11.1 Text 모드 (run_cohort, mode="text")
LLM이 페르소나 프로필 + URL/task로 행동을 **한 번에 예측**. 실 브라우저 없음.

```
CohortRunner
  ├── persona_store.read_persona × N   (overlay)
  ├── ThreadPoolExecutor(max_workers)
  │   └── [for each persona]
  │       └── provider_router.call(LLM, persona_prompt + task)
  │           → returns {outcome, conversion_probability, reasoning, ...}
  └── cohort_results/<id>.json 저장
```

**비용**: ~1,200 input + 1,000 output 토큰/페르소나 × Sonnet 4.6 ≈ **$0.02/페르소나**.
**속도**: 5 페르소나 병렬 ≈ **20초**.
**주의**: observation을 append하지 **않음** (실측 없이 예측만).

### 11.2 Browser 모드 (run_session / run_cohort mode="browser")
Playwright로 실제 사이트 조작, 턴마다 LLM이 plan → action 결정.

```
agent_loop.run_session
  ├── persona_store.read_persona            (overlay: soul + past observations)
  ├── browser_runner.launch_browser
  ├── [turn 1..MAX_TURNS=10]
  │   ├── provider_router.call(plan, persona + past_obs + page)
  │   ├── browser_runner._dispatch(action)  (9 원시 액션)
  │   │   └── 셀렉터 실패 → vision_clicker fallback
  │   ├── provider_router.call(decision_judge, 스크린샷)
  │   └── persona_store.append_observation  (workspace에 영구 저장)
  ├── post_session_end hook → review_agent.inspect
  └── sessions/<id>.json 저장
```

**9 원시 액션**: `click`, `fill`, `select`, `scroll`, `wait`, `read`, `navigate`, `back`, `close_tab`.
**비용**: ~5,000 input + 3,000 output 토큰/턴 × 4~10턴 ≈ **$0.20~0.50/세션**.
**속도**: 2~5분/세션.

---

## 12. 진화 메커니즘 (Memory Stream + Reflection)

Park et al. 2023 "Generative Agents" 계열. 세션마다 축적되는 **append-only 메모리**가 다음 세션의 행동을 바꾼다.

### 12.1 3층 구조

| 층 | 파일 | 생성 시점 |
|---|---|---|
| **Soul** (identity) | `soul/vNNN.md` | create_persona / 신규 version (H1에선 수동) |
| **Observation** (raw) | `history/o_XXX.json` | 매 턴 자동 append (browser 모드) |
| **Reflection** (higher-order) | `reflections/r_XXX.json` | 수동 트리거 — level1 패턴 / level2 cross-context |

### 12.2 읽기 경로 (read_persona 호출 시)
```
read_persona("p_pragmatic")
  ├── soul_dir = _find_dir("p_pragmatic", "soul")
  │       (workspace 우선, 없으면 builtin)
  ├── manifest → current_version → soul_text
  ├── observations = [workspace/p_pragmatic/history/*] ∪ [builtin/p_pragmatic/history/*]
  │                  시간순 정렬, obs_id dedup
  └── reflections = 동일 머지
```

### 12.3 실전 예시 (앞서 돌린 세션)

세션 전: `p_pragmatic/history/` 20 파일 (이전 세션들의 누적).
세션 후: **24 파일 (+4)**. 네 번의 관찰:
1. 홈페이지 구조 인식 → "뉴스 블록 찾기" plan
2. 상단 바로가기 클릭 시도
3. 직접 IT/과학 URL로 navigate
4. 헤드라인 읽기 → task_complete 판단

다음 세션에서 같은 `p_pragmatic`을 사용하면, plan 단계의 LLM 프롬프트에 **이 24개 observation이 요약되어 주입**됨 → "내가 네이버를 가본 적 있고, 상단 바로가기는 셀렉터가 잘 안 걸리더라" 같은 경험이 행동에 반영.

### 12.4 Reflection 합성 (H1은 수동)
```python
from persona_agent.lowlevel import append_reflection

# level1: 패턴 인식 (10+ observation에서 공통 주제 추출)
append_reflection(
    persona_id="p_pragmatic",
    level=1,
    text="네이버 메인의 상단 바로가기 셀렉터가 불안정함. 직접 URL navigate가 더 빠름.",
    sources=["o_91564488ca89f274", "o_308de24a3cf8d87f"],
)

# level2: cross-context 합성 (여러 사이트 경험 통합)
append_reflection(
    persona_id="p_pragmatic",
    level=2,
    text="한국 포털은 광고/콘텐츠 밀도가 높아 탐색 우선 전략이 효과적.",
    sources=["r_level1_naver", "r_level1_daum"],
)
```

reflection도 immutable. 다음 세션 `read_persona` 호출 시 자동 컨텍스트로 주입.

---

## 13. SaaS 통합 패턴

### 13.1 권장 아키텍처 (동기 라이브러리 + 외부 큐)

```
[FastAPI endpoint]
   POST /analyses
        ├── 입력 검증
        ├── job_id = uuid
        ├── DB: INSERT job (status=queued)
        ├── Celery/RQ: enqueue(job_id)
        └── return 202 {job_id}

[Celery worker]
   run(job_id):
      job = DB.get(job_id)
      workspace_dir = f"/var/persona_jobs/{job.tenant}/{job_id}"

      # 1. configure
      import persona_agent as pa
      pa.configure(pa.Workspace(
          root=Path(workspace_dir),
          personas_dir=Path(workspace_dir)/"personas",
          builtin_personas_dir=None,  # 번들 사용
          prompts_dir=None,
          config_dir=None,
          reports_dir=Path(workspace_dir)/"reports",
      ))

      # 2. 실행
      from persona_agent.lowlevel import run_cohort, generate_cohort_report
      try:
          result = run_cohort(job.cohort_id, job.url, job.task, mode="text")
          report_id = generate_cohort_report(result["output_path"])
      except pa.PersonaAgentError as e:
          DB.update(job_id, status="failed", error=str(e))
          return

      # 3. 결과 저장
      DB.update(job_id, status="done", report_id=report_id,
                result_path=result["output_path"])
```

### 13.2 멀티테넌시

- 한 프로세스당 하나의 `configure()`. 스레드 안전성은 SaaS가 책임.
- 테넌트별 격리가 필요하면 **워커 프로세스를 테넌트당 하나**로 (Celery route 사용).
- 또는 `contextvars` 기반 workspace 스위치 (0.3.0+ 로드맵).

### 13.3 비용 모니터링
```python
# core.metrics가 자동으로 events.jsonl에 토큰 수 기록
# 수집:
from persona_agent._internal.core.metrics import summary
s = summary(days=7)  # {"total_tokens": ..., "total_cost_usd": ..., "sessions": ...}
```

---

## 14. 예외 처리 패턴

```python
import persona_agent as pa
from persona_agent.lowlevel import run_session

try:
    log = run_session("p_pragmatic", url, task)
except pa.BrowserError as e:
    # playwright 타임아웃, 내비게이션 실패
    logger.warning("browser failed, falling back to text mode: %s", e)
    result = run_cohort_text_fallback(...)
except pa.VisionError as e:
    # Vision 좌표 추출 실패
    log_event({"type": "vision_fail", "url": url})
except pa.LLMError as e:
    # provider 오류 / 예산 초과 / JSON 파싱 실패
    raise  # 재시도는 상위 큐에서
except pa.PersonaAgentError as e:
    # 예상치 못한 모든 경우
    logger.exception("session failed")
    DB.update(job_id, status="failed", error=str(e))
```

---

## 15. 테스트 구조

### 15.1 persona_agent/tests (70 테스트)

```
tests/
├── test_smoke.py                      파사드 공개 API, 예외, Settings (9)
├── test_persona_store.py              legacy persona_store 핵심 (8, 41r에서 이동)
├── test_version_manager.py            버전 관리 (9)
├── test_cohort_runner.py              retry, graceful degradation (11)
├── test_cohort_report.py              Wilson CI, 집계 (10)
├── test_hallucination_guard.py        숫자·p-value·claim 검증 (12)
├── test_persona_overlay.py            PR-8 오버레이 (6)
├── test_pure_analysis_import.py       optional extras lazy 보장 (2)
├── test_data_files_accessible.py      번들 데이터 접근 (3)
└── test_workspace_isolation.py        workspace 격리 (2)

conftest.py: 세션 스코프 자동 workspace (tmp dir + 번들 데이터)
```

### 15.2 41r/tests (49 테스트, 기존 유지)
같은 테스트들이 `persona_agent._internal.*` import로 전환되어 있음. 개발 중 `make test`로 돌아감.

### 15.3 실행
```bash
# persona_agent 단독
cd persona_agent && pytest -q           # 70 tests

# 41r 통합
cd 41r && make test                     # 49 tests
cd 41r && make verify                   # test + audit
cd 41r && make verify-all               # 전체 파이프라인 (render + tag + audit)
```

---

## 16. 개발 워크플로

### 16.1 새 기능 추가
1. `_internal/<group>/`에 구현
2. `lowlevel.py`에 re-export (공개가 필요하면)
3. 테스트 `persona_agent/tests/`에 작성
4. `make test` 녹색 확인
5. 번들 데이터 변경 시 `cd persona_agent && python -m build --wheel` 재빌드

### 16.2 의존성 추가 기준
- **base** (`pyproject.toml [project] dependencies`): import 시점 항상 필요한 것만 (anthropic, yaml, jinja2)
- **extras**: 특정 기능에서만 쓰는 것 → lazy import + `MissingExtraError` wrapping
  ```python
  def _pd():
      try: import pandas as pd
      except ImportError as e:
          raise MissingExtraError("benchmark", "pip install persona-agent[benchmark]") from e
      return pd
  ```

### 16.3 구조 재배치 (`_internal/` 내부)
자유. 공개 API(`lowlevel.py`, `__init__.py`)만 안정적으로 유지하면 semver minor bump 안 해도 됨.

### 16.4 디버깅 팁
- `.venv/bin/python3 -m persona_agent._internal.<group>.<module>` 로 CLI 직접 실행 가능
- 세션 로그는 `workspace/events/events.jsonl`에 자동 append (ANTHROPIC tokens 포함)
- `grep "persona_id.*p_xxx" events/events.jsonl` 로 특정 페르소나 히스토리 추적

---

## 17. 로드맵 (현재 0.2.0.dev0)

| 버전 | 내용 |
|---|---|
| **0.2.0 (현재)** | 단일 패키지, lowlevel sync API, overlay 저장소 |
| 0.2.1 | CLI entry points (`persona-agent-audit` 등) |
| **0.3.0** | 비동기 job API (`submit_analysis/get_status/get_result`), contextvars 멀티테넌시 |
| 0.4.0 | 자동 reflection synthesis (H2 범위), browser 모드 session budget 강제 |
| 1.0.0 | 공개 PyPI, shim 삭제, semver 안정화 |

---

## 18. 참고

- 리팩터 플랜: `/home/kimtayoon/.claude/plans/sorted-giggling-puzzle.md`
- 원 리포 문서: `/home/kimtayoon/myrepo/41r-advisor/41r/STATUS.md`, `41R-Constitution.md`
- H1 가설 v2: `41R-Slice-H1.md`
- 검증 결과: `41r/experiments/ablation/` (n=200, p=0.000009)
- 이 문서 작성 중 돌린 실전 테스트:
  - Slack pricing: `cohort_results/cohort_manual5_140010_c34f.json`
  - naver.com text: `cohort_results/cohort_manual5_014420_6589.json`
  - naver.com browser (p_pragmatic, 4턴): `sessions/s_b80b51a5*.json`
