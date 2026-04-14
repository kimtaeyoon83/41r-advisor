# 41R Advisor — Project Guidelines

## 프로젝트 개요

41R Persona Market — AI 페르소나 기반 예측 A/B 테스트 시스템.
캘리브레이션된 페르소나가 실제 브라우저에서 제품을 사용하고, 세그먼트별 행동 비교 리포트를 생성한다.

**핵심 문서**: `41R-Constitution.md` (구조), `41R-Slice-H1.md` (현재 범위), `41R-Browser-Testing-Playbook.md` (행동 규칙)

## 코드 위치

```
41r/                          메인 코드 디렉토리 (여기서 python3 실행)
  modules/                    M1~M7 + 보조 모듈
  core/                       Provider Router, Cache, Events Log, Hooks
  prompts/agent/              Hot Zone 프롬프트 (v001.md + manifest.yaml)
  config/research/            LLM 라우팅, 캐시 설정
  personas/p_XXX/soul/        페르소나 정의 (versioned)
  experiments/                검증 결과, 아웃바운드 자료
  .venv/                      Python 가상환경 (uv)
```

## 실행 환경

```bash
cd /home/kimtayoon/myrepo/41r-advisor/41r
source .venv/bin/activate  # 또는 .venv/bin/python3 직접 사용
# API 키는 .env 파일에 ANTHROPIC_API_KEY=...
```

## 핵심 지침

### Architecture

- **Stable Core / Hot Zone 분리**: 판단 로직은 코드에 박지 않는다. 항상 `prompts/`에서 로드
- **Versioned Document 패턴**: 모든 변경은 새 파일 (v001→v002). 롤백 = manifest.current 변경
- **Review Agent → proposals/ 전용 쓰기**: prompts/에 직접 쓰지 않음. Version Manager만 쓰기 권한
- **Constitution 고정**: Sprint 종료 시점에만 revision. 그 외엔 `experiments/constitution_notes/`에 메모

### 브라우저 자동화

- **Vision Mode 필수**: decision_judge는 스크린샷을 보고 판단 (A11y tree 아님)
- **Vision Click fallback**: 텍스트 셀렉터 실패 시 자동으로 스크린샷 좌표 클릭
- **셀렉터 메모리**: `cache/selector_memory/`에 사이트별 성공/실패 전략 기록
- **9개 원시 액션만**: click, fill, select, scroll, wait, read, navigate, back, close_tab
- **셀렉터는 텍스트+역할 기반**: XPath/CSS/id 직접 사용 금지

### 페르소나

- **Soul v002 구조 사용**: 5개 성향 프로필 + 세대 특성 + 좌절 트리거 + 신뢰 기준 + voice_sample
- **soul 수정 시 상황-반응 테스트 필수**: `experiments/ab_results/persona_situation_response_test.md` 참조
- **Reflection은 immutable**: 새 합성은 새 파일. 수정 금지

### LLM 비용

- **H1에서는 Opus 사용 금지**: plan도 Sonnet, advisor OFF (`config/research/llm_routing/routing.yaml`)
- **Vision clicker는 Haiku**: 좌표 식별은 Haiku로 충분
- **MAX_TURNS=10**: 비용 최적화. v4-full에서 30으로 복원
- **세션당 예상 비용 ~$0.3~0.5**

### 코드 품질

- **silent except 금지**: 모든 except에 logger.debug/warning 필수
- **path traversal 검증**: persona_id, prompt_path에 `.resolve()` + `is_relative_to()` 필수
- **thread-safe 싱글턴**: `threading.Lock` 사용 (provider_router, cache)
- **navigate URL 검증**: http/https만 허용
- **파일 I/O**: append-only 패턴, 덮어쓰기 금지 (observation, session log)

### 리포트

- **분석 레이어 필수**: 세션 로그 → `report_analyzer.py` LLM 분석 → HTML 리포트
- **lineage.json 동반**: 모든 리포트에 프롬프트 버전, 모델 라우팅, 페르소나 스냅샷 포함
- **HTML escape**: 유저 데이터를 리포트에 넣을 때 `html.escape()` 사용

### 검증

- **상황-반응 테스트**: Part A(방향성) + Part B(세밀함) 이중 구조
- **새 페르소나 추가 시 반드시 테스트 실행**
- **벤치마크 매핑 시 단위 확인**: 초 vs 턴, 단어% vs 액션% 등 단위가 다르면 방향성만 비교
- **할루시네이션 체크**: 리포트 생성 후 세션 로그와 대조 검증 필수

### 절대 하지 않을 것 (Constitution 12장)

- Mabl/Testim/QA Wolf와 정면 경쟁
- 벡터 DB (파일 + Memory Stream으로 충분)
- Git을 시스템 컴포넌트로 사용
- Meta-Agent 자동 적용 (Review Agent 제안은 항상 승인 필요)
- "synthetic reviews" 워딩 (FTC 위반)
- 페르소나 개별 정확도 주장 (cohort 단위로만)

## 자주 쓰는 명령어

```bash
# 세션 실행
ANTHROPIC_API_KEY=$(cat .env | cut -d= -f2) .venv/bin/python3 -c "
from modules.agent_loop import run_session
log = run_session('p_impulsive', 'https://example.com', 'task description')
"

# 리포트 생성
from modules.report_gen import generate_report
report_id = generate_report(session_list, persona_ids, 'ab')

# Review Agent CLI
.venv/bin/python3 -m modules.review_agent inspect <session_id>
.venv/bin/python3 -m modules.review_agent evaluate <session_id>

# LLM 라우팅 변경
# config/research/llm_routing/routing.yaml 수정 후 reload
from core.provider_router import reload_config; reload_config()
```
