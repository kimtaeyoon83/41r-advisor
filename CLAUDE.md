# 41R Advisor — Project Guidelines

## 프로젝트 개요

41R Persona Market — AI 페르소나 기반 **세그먼트 분기 진단** 시스템.
캘리브레이션된 페르소나가 실제 브라우저에서 제품을 사용하고, "**어떤 사람 타입이 어떻게 다르게 반응하는지**" 진단 리포트를 생성한다.

**현재 상태 (2026-04-14)**: H1.1 marginal value 통계 입증 완료 (n=200, p=0.000009). 시장 검증(F1) 대기.

**핵심 문서**: `41R-Constitution.md` (구조), `41R-Slice-H1.md` (현재 범위), `41R-Browser-Testing-Playbook.md` (행동 규칙), `41r/STATUS.md` (현재 상태), `41r/reports/EXECUTIVE_REPORT.html` (사업팀용)

## 코드 위치

```
41r/                          메인 코드 디렉토리 (여기서 python3 실행)
  modules/                    M1~M7 + 코호트 + 벤치마크 로더 + 할루시네이션 가드
  core/                       Provider Router, Cache, Events Log, Hooks, Metrics
  prompts/agent/              Hot Zone 프롬프트 (agent/ + report/)
  config/research/            LLM 라우팅, 캐시 설정
  personas/                   수동 10개 + demo 5개 + 자동 생성 코호트
  experiments/                검증 결과, 아웃바운드, Ablation, 외부 데이터셋
  reports/                    생성된 리포트 (EXECUTIVE, SIMPLE, cohort)
  tests/                      pytest unit tests (49건)
  secrets/                    GCP 키 등 (gitignored)
  .venv/                      Python 가상환경 (uv)
  Makefile                    make test / audit / verify
```

## 실행 환경

```bash
cd /home/kimtayoon/myrepo/41r-advisor/41r
source .venv/bin/activate  # 또는 .venv/bin/python3 직접 사용
# API 키는 .env 파일에 ANTHROPIC_API_KEY=...
# GCP 키는 secrets/gcp-bigquery.json (gitignored)
```

---

## 🎯 핵심 포지셔닝 (H1 피벗 후, 절대 위반 금지)

### 판매 메시지 — 이걸로만 팔기
> "PM의 변경 아이디어 10개 중, A/B 테스트 **전에** 세그먼트별로 갈리는 3개를 **24시간 · 건당 ~$5**에 식별합니다."

### 검증된 가치 (n=200, p=0.000009)
**세그먼트 분기 탐지** (sample 타입별 반응 차이 찾기) — Demo-only baseline 대비 +16%p.

### 파는 것 vs 안 파는 것
| ✅ 팔 수 있는 것 | ❌ 팔면 안 되는 것 |
|---|---|
| "세그먼트별 반응이 갈린다" 진단 | "정확한 전환율 X%" 예측 |
| "A보다 B가 나을 것" 상대 비교 | "+Y% lift 보장" 같은 lift 약속 |
| 이탈 이유 정성 분석 | "AI가 정답을 알려준다" |
| "단일 variant vs 세그먼트별 설계" 판단 | "A/B 테스트 대체" |

### H1 가설 v2 + Kill Criteria (단계화)
```
H1: CPO/Head of Growth는 "세그먼트 분기 진단"에 건당 ~$5 예산을 낼 의향이 있다.

단계별 Kill:
  발송 → 응답:      30건 중 <3 = Kill / ≥5 = Pass
  응답 → 샘플 요청:  5건 중 0 = Kill / ≥3 = Pass
  샘플 → 미팅:      3건 중 0 = Kill / ≥2 = Pass
  미팅 → 유료 의향:  2건 중 0 = Kill / ≥1 = Pass
  의향 → 결제:      $5+ 0건 = Kill / 1건+ = Pass
```

---

## 🔴 절대 금지 (추가 업데이트)

**Constitution §12 + 이번 세션 피벗**:
- ❌ Mabl/Testim/QA Wolf와 정면 경쟁
- ❌ 벡터 DB (파일 + Memory Stream으로 충분)
- ❌ Git을 시스템 컴포넌트로 사용
- ❌ Meta-Agent 자동 적용
- ❌ **"synthetic reviews" 워딩** (FTC 위반)
- ❌ **"예측 A/B 테스트" 워딩** (n=200 결과 정확도 무의미)
- ❌ **절대 전환율 수치 주장** (GA4 대비 14~19× over, 80× for CTR)
- ❌ **페르소나 개별 정확도 주장** (cohort 단위로만)
- ❌ **"+Y% lift" 약속** (실측 cross-check 0건)

---

## 핵심 지침

### Architecture

- **Stable Core / Hot Zone 분리**: 판단 로직은 코드에 박지 않는다. 항상 `prompts/`에서 로드
- **Versioned Document 패턴**: 모든 변경은 새 파일 (v001→v002). 롤백 = manifest.current 변경
- **Review Agent → proposals/ 전용 쓰기**: prompts/에 직접 쓰지 않음. Version Manager만 쓰기 권한
- **Constitution 고정**: Sprint 종료 시점에만 revision. 그 외엔 `experiments/constitution_notes/`에 메모
- **Hot Zone 확장**: `prompts/agent/` + `prompts/report/` 둘 다 lineage 추적

### 코호트 시스템 (핵심)

- **multiprocessing.Pool (spawn) 사용**: ThreadPoolExecutor는 asyncio event loop 충돌
- **Browser mode max_workers=3 강제**: Chromium 메모리 부담
- **max_retries=2**: browser session 실패 시 자동 재시도
- **persona_generator**: Latin Hypercube sampling으로 15명+ 자동 생성
- **cohort_report는 benchmark_loader 통합**: GA4 baseline 자동 비교

### 외부 공개 데이터셋 (Tier 1 — 상업 이용 가능)

| 데이터셋 | 라이선스 | 용도 | 경로 |
|---|---|---|---|
| Upworthy Research Archive | CC BY 4.0 | A/B 검증 (n 확장) | `experiments/datasets/upworthy/` |
| GA4 Sample (BigQuery) | Public | 절대 수치 reality check | `experiments/datasets/ga4_sample/` |
| Open Bandit (ZOZO) | CC BY 4.0 | CTR sanity check | `experiments/datasets/open_bandit/` |

**사용 정책**:
- 상업 자료(아웃바운드)에는 Tier 1만 인용
- RetailRocket, Coveo, H&M Kaggle 등은 NC-SA라 **R&D only**
- 새 데이터셋 추가 시 `experiments/constitution_notes/external_benchmarks.md`에 등재

### 브라우저 자동화

- **Vision Mode 필수**: decision_judge는 스크린샷을 보고 판단 (A11y tree 아님)
- **Vision Click fallback**: 텍스트 셀렉터 실패 시 자동으로 스크린샷 좌표 클릭
- **셀렉터 메모리**: `cache/selector_memory/`에 사이트별 성공/실패 전략 기록
- **9개 원시 액션만**: click, fill, select, scroll, wait, read, navigate, back, close_tab
- **셀렉터는 텍스트+역할 기반**: XPath/CSS/id 직접 사용 금지

### 페르소나 (15명 풀)

- **수동 정의 10명**:
  - 기본 5: p_impulsive, p_cautious, p_budget, p_pragmatic, p_senior
  - 확장 5: p_b2b_buyer, p_genz_mobile, p_parent_family, p_creator_freelancer, p_overseas_kor
- **Demo baseline 5명**: nnage/gender/job만 (ablation 비교용)
- **Soul v002 구조**: 5개 성향 프로필 + 세대 특성 + 좌절 트리거 + 신뢰 기준
- **신규 페르소나 추가 시 manifest.yaml 필수** + history/, reflections/, snapshots/ 디렉토리
- **Reflection은 immutable**: 새 합성은 새 파일. 수정 금지

### LLM 비용

- **H1에서 Opus 사용 금지**: plan도 Sonnet, advisor OFF
- **Vision clicker는 Haiku**
- **MAX_TURNS=10**: 비용 최적화
- **세션당 ~$0.3~0.5**, **코호트 n=200 ablation ~$30**

### 데이터 무결성 (이번 세션 추가)

- **Hallucination Guard 필수**: 모든 리포트는 `make audit` 통과
- **Claim 태깅**: `<span data-src="file.json:field">값</span>` 핵심 숫자 명시
- **p-value 자동 재계산**: scipy로 원본 데이터에서 검증
- **외부 데이터셋 ground truth**: reports/, experiments/ablation/, experiments/ab_validation/, experiments/datasets/{ga4,open_bandit}/ 자동 스캔
- **Audit trail**: `make audit-trail` — 각 숫자별 출처 추적 보고서

### 코드 품질

- **silent except 금지**: 모든 except에 logger.debug/warning 필수
- **path traversal 검증**: persona_id, prompt_path에 `.resolve()` + `is_relative_to()` 필수
- **thread-safe 싱글턴**: `threading.Lock` 사용 (provider_router, cache)
- **navigate URL 검증**: http/https만 허용
- **파일 I/O**: append-only 패턴, 덮어쓰기 금지 (observation, session log)
- **Unit test 필수**: 새 모듈 추가 시 tests/ 에 테스트 작성
- **Release 전 make verify**: test + audit 둘 다 통과

### 리포트

- **분석 레이어 필수**: 세션 로그 → `report_analyzer.py` LLM 분석 → HTML 리포트
- **lineage.json 동반**: 모든 리포트에 프롬프트 hash, 모델 라우팅, 페르소나 스냅샷 포함
- **HTML escape**: 유저 데이터를 리포트에 넣을 때 `html.escape()` 사용
- **타겟별 분리**:
  - `EXECUTIVE_REPORT.html` — 사업팀용 (통계/근거 포함)
  - `SIMPLE_REPORT.html` — 일반인용 (담담한 설명, 외부 데이터 샘플 포함)
  - `sample_report_v2.html` — 종합 진단 + Reality Check
  - `cohort_rpt_*/` — 사이트별 세부 진단
- **Reality Check 섹션 필수**: 절대 수치 주장 시 GA4 baseline과 비교 명시
- **사이트별 finding은 Appendix**: 메인 근거는 n=200 ablation, 사이트별은 Appendix (실측 cross-check 0건이라)

### 검증

- **상황-반응 테스트**: Part A(방향성) + Part B(세밀함) 이중 구조
- **새 페르소나 추가 시 반드시 테스트 실행**
- **Ablation Study 방법론 확정**:
  - Arm A (Demo-only) vs Arm B (41R): 같은 LLM, 같은 seed, 같은 케이스
  - n=200 Upworthy로 통계 power 확보 (McNemar paired test)
  - Cache disabled 모드 명시
- **GA4/Open Bandit reality check 필수**: 절대 수치 주장 전 benchmark_loader로 자동 비교
- **할루시네이션 체크**: 리포트 생성 후 `make audit`로 세션 로그·외부 데이터와 대조 검증

---

## 자주 쓰는 명령어

### 개발 워크플로
```bash
make test              # 49 unit tests
make test-cov          # 커버리지 포함
make audit             # 모든 리포트 hallucination guard
make audit-trail       # 출처 추적 보고서 생성
make verify            # test + audit (release 전 필수)
```

### 세션/코호트 실행
```bash
# 단일 세션
ANTHROPIC_API_KEY=$(cat .env | cut -d= -f2) .venv/bin/python3 -c "
from modules.agent_loop import run_session
log = run_session('p_impulsive', 'https://example.com', 'task description')
"

# 코호트 실행 (text mode = 빠름·저렴, browser mode = 실측)
.venv/bin/python3 -m modules.cohort_runner <cohort_id> <url> <task> [text|browser]

# 코호트 생성 (자동)
.venv/bin/python3 -c "
from modules.persona_generator import CohortSpec, generate_cohort
spec = CohortSpec(segment_name='20대 여성 직장인', size=20, age_range=(22,29), ...)
run_id = generate_cohort(spec)
"

# 리포트 생성
.venv/bin/python3 -m modules.cohort_report cohort_results/<result>.json
```

### 검증
```bash
# n=200 ablation 재실행 (Upworthy)
.venv/bin/python3 experiments/ablation/run_ablation_n200.py

# A/B 역검증 v3
.venv/bin/python3 experiments/ab_validation/run_validation_v3.py

# 외부 baseline 로드 + 코호트 비교
.venv/bin/python3 -m modules.benchmark_loader reports/<cohort>/aggregation.json
```

### LLM 라우팅 변경
```python
# config/research/llm_routing/routing.yaml 수정 후
from core.provider_router import reload_config
reload_config()
```

### 시스템 메트릭
```bash
.venv/bin/python3 -m core.metrics summary       # 최근 7일
.venv/bin/python3 -m core.metrics dashboard     # dashboard.json
```

---

## H6 법률 리스크 (진행 전 체크)

- **FTC synthetic reviews 규정**: 워딩 조심 ("가상 리뷰", "AI 생성 리뷰" 금지)
- **k-anonymity**: 페르소나의 연령+지역+직업 조합 5개 이상 데이터 조합 주의
- **외부 데이터셋 라이선스**: CC BY-NC-SA 데이터는 상업 자료에 인용 금지
- **Service Account JSON 보호**: `secrets/` 디렉토리 gitignored

상세: `experiments/legal_review/H6_legal_questions.md`

---

## 현재 주요 태스크 (상태)

### ✅ 완료
- H1.1 marginal value 통계 입증 (n=200, p<0.001)
- H1.2 행동 벤치마크 일치 (6/6)
- 시스템 인프라 + 49 unit tests + CI + hallucination guard
- EXECUTIVE_REPORT + SIMPLE_REPORT + 5 사이트 코호트
- 외부 데이터셋 3종 통합 (Upworthy, GA4, Open Bandit)
- H1 가설 v2 피벗 (단계화 Kill Criteria)

### ⏳ 사용자 결정 대기
- **F1**: CPO 5~10명 발송 결정 → 시장 검증 시작
- **F2**: 파트너사 NDA 협의 → 실제 GA cross-check (H2 진입 결정)
- **H6**: 법률 자문 의뢰 (FTC + k-anonymity)

---

## GitHub / 자료

- Repo: https://github.com/kimtaeyoon83/41r-advisor
- SSH alias: `git@github.com-kimtaeyoon83:kimtaeyoon83/41r-advisor.git`
- 시작점: `reports/index.html` (전체 인덱스)
- 상태 요약: `41r/STATUS.md`
