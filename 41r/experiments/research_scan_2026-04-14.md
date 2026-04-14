# Phase L+1 — 시스템/연구 조사 결과 (2026-04-14)

> 사용자 결정: 발송 보류, 시스템 견고성 + 외부 연구 정합성을 먼저 다지기로 함.
> 본 문서는 (1) 코드 개선 이행 결과, (2) 최신 연구 시사점, (3) 기능-결과 연결 검토 결과를 한 곳에 정리.

---

## 1. 이번 세션에 구현한 것

### A. Tier 1 — 발송 전 방어력 (총 ~6h)

| # | 작업 | 파일 | 검증 |
|---|---|---|---|
| 1 | **자동 Reality Check 통합** | `modules/cohort_report.py` (+`benchmark_loader` 호출) | cohort_rpt_20260414_b7fc94 — 3개 비교 자동 생성, summary "2/3 over-estimate" |
| 2 | **p-value freshness 검증** | `modules/hallucination_guard.py` (+`mcnemar` 재계산) | McNemar 재계산 = 9.06e-6 ≈ 보고서 p=0.000009 ✅ |
| 3 | **Bootstrap CI on +16%p** | `experiments/ablation/bootstrap_ci.py` | n=200, 1000회 → **분기 +16%p (95% CI [+9.50, +22.51]%p)** ✅ 0 미포함 |
| 4 | **Claim 태깅 자동화** | `modules/claim_tagger.py` | EXECUTIVE_REPORT 태그 1→14 (high-confidence만 자동 적용) |

### C. EconML CATE Validator (H2 진입 차별화 카드)

- 신규: `modules/cate_validator.py`
- 학술 근거: Chernozhukov et al., Econometrica 2025년 7월 — Generic ML Inference on HTE
- 작동 모드:
  - EconML 설치 시 → CausalForestDML
  - 미설치 시 → segment-level naïve CATE + bootstrap CI (현재 default)
- 합성 데이터 검증: 41R 예측 vs 실제 CATE → F1=0.80, 승자 정확도 67% — 워크플로우 정상
- **경쟁사 중 누구도 이거 안 함** (UXAgent, Aaru 모두 미통합)

### Bootstrap CI 핵심 발견

```
분기 탐지 +16.0%p (95% CI: [+9.50, +22.51]%p)  ✅ 효과 통계적으로 실재
정확도   -6.0%p (95% CI: [-12.01, +0.00]%p)   ⚠️ Demo와 유의차 없음 — 우리 강점 아님
```

→ "분기 탐지가 가치, 승자 예측은 아님"이라는 H1 v2 피벗에 **추가 통계 근거** 확보.

---

## 2. 최신 연구 — F1 발송 자료 강화 포인트

### ⭐ 인용해야 할 핵심 문헌

| 문헌 | 시사점 | 어디에 인용 |
|---|---|---|
| **Rank-Preserving Calibration (RAPCal, OpenReview 2025)** | 상대 순위는 보존, 절대 수치는 보존 안 됨 | "절대 14~19× over, 상대만 판매" 논리 뒷받침 |
| **Park et al., Generative Agents 1,000 People (Stanford 2024, arXiv 2411.10109)** | 2시간 인터뷰 페르소나로 GSS 응답 85% 재현 | "AI 페르소나 검증 가능성" 카테고리 신뢰 |
| **Chernozhukov, Econometrica 2025/07 — HTE Inference** | EconML CATE의 canonical reference | F2 NDA 파트너 만날 때 검증 방법론 |
| **Lin (2025) "Six Fallacies"** | LLM으로 인간 참여자 대체 시 6가지 오류 | 모든 리포트 헤더에 선제 인정 |
| **TechCrunch 2025/12 — Aaru $1B Series A** | 합성 리서치 카테고리 펀딩 검증 | F1 deck "허공에 파는 거 아님" |

### 경쟁 좌표

| 카테고리 | 누구 | 41R 차이 |
|---|---|---|
| 합성 폴링 | Aaru, Listen Labs, Outset | 우리는 **behavioral on live product** (설문 ❌) |
| AI 학술 페르소나 | UXAgent (CHI 2025), Customer-R1 | 우리는 **상업화 + 통계 입증** (학술 ❌) |
| Vision 브라우저 에이전트 | Stagehand, Open Operator (Browserbase) | 우리는 **persona+report stack** ($5/run 가능 이유) |
| UX 테스트 도구 | Maze, UserTesting, Lyssna | 이들 **AI 페르소나가 직접 사이트 쓰는 기능 0** = 공백 |

### 규제 (선제 대응)

- **FTC Consumer Review Rule** — 2025/12/22 첫 경고 10건 (위반당 $53,088)
  - 41R은 리뷰 생성 ❌, 직접 적용 안 됨. 워딩 실수만 조심.
- **EU AI Act Article 50** — Dec 2025 transparency Code of Practice
  - 모든 리포트 헤더에 "AI-generated synthetic research, not consumer reviews" 라벨

---

## 3. 기능-결과 연결 검토 (Orphan 검출)

전수 조사로 발견한 **연결 끊긴 코드/데이터**:

### 🔴 Critical (이번 세션에 해결)
- **`benchmark_loader` ↔ `cohort_report` 미연결** → ✅ 해결 (Task #1)

### 🔴 Critical (남음 — 사용자 결정 필요)
- **`modules/provenance.py` = NotImplementedError 빈 stub**
  - 어디에서도 import 안 됨
  - 권고: (a) HMAC-SHA256 chain으로 lightweight 구현 (H2 감사 대비), 또는 (b) 삭제 + CLAUDE.md에서 M4 언급 제거
  - **결정 필요**

### 🟡 Stale (정리 권고)
- **사용 안 된 페르소나 10명**: `demo_*` (5명) + `p_b2b_buyer`, `p_genz_mobile`, `p_parent_family`, `p_creator_freelancer`, `p_overseas_kor` (5명)
  - cohort_results/*.json 어디에도 등장 안 함
  - demo_* 5명은 ablation에 사용됨 — 유지 필요
  - 확장 5명(p_*)은 정의만 되고 한 번도 안 돌려봄
  - 권고: 확장 5명 중 1~2명은 작은 코호트 1번씩 돌려서 검증, 안 쓸 거면 archive

- **링크 안 된 리포트 5개**: `EXECUTIVE_REPORT.html`, `SIMPLE_REPORT.html`, `sample_report_v1.html` + 옛 cohort 2개
  - index.html에서 EXECUTIVE/SIMPLE 미연결 → STATUS.md/외부 자료에서 직접 참조 중
  - 권고: index.html 업데이트 (사업팀용/일반인용 카드 추가) — 5분 작업

- **빈 config 파일**: `config/research/reflection_triggers/triggers.yaml`
  - 어디에서도 로드 안 됨
  - 권고: 삭제 또는 H2 reflection trigger 구현 시 유지

### 🟢 Future hooks (intentional, OK)
- prompts/ versioning은 모두 정상 작동
- selector_memory.py는 browser_runner와 연결됨 (orphan 아님)
- GA4/Open Bandit datasets — benchmark_loader 통해서만 접근 (이번에 해결됨)

---

## 4. 권장 다음 단계 (사용자 결정)

### 🟢 빠른 정리 (30분 이내)
1. `index.html`에 EXECUTIVE/SIMPLE 카드 추가
2. `provenance.py` — 삭제 vs. lightweight 구현 결정
3. 옛 cohort 리포트 2개 archive로 이동
4. `config/research/reflection_triggers/` 삭제

### 🟡 발송 전 마지막 점검 (1~2시간)
1. 모든 리포트 헤더에 "AI-generated synthetic research, not consumer reviews" 라벨 추가
2. EXECUTIVE_REPORT/SIMPLE_REPORT에 RAPCal + Park 2024 인용 footnote 1줄
3. 면책 페이지 (`reports/methodology_disclaimer.html`) 신규 — Lin "Six Fallacies" + 한계 명시
4. `make audit` 통과 확인

### 🔵 F2 진입 카드 (NDA 파트너 확보 시)
1. `cate_validator.py` 정식 가동 — econml 설치 + 실제 A/B 데이터로 검증
2. 결과 → "41R 예측 vs 실제 CATE F1 일치도" 형식 보고서 생성
3. 경쟁사 누구도 안 하는 차별점

---

## 5. 통계 (이번 세션)

- **추가/수정 파일**: 6개
  - 신규: `modules/claim_tagger.py`, `modules/cate_validator.py`, `experiments/ablation/bootstrap_ci.py`, `experiments/research_scan_2026-04-14.md`
  - 수정: `modules/cohort_report.py`, `modules/hallucination_guard.py`
- **테스트**: 49 통과 유지
- **신뢰구간 신규**: divergence +16%p [+9.5, +22.5]%p 95% CI
- **Reality Check 자동화**: 모든 cohort 리포트에 GA4/Open Bandit 비교 자동 첨부
- **Orphan 발견**: 1 critical (해결), 4 stale (정리 권고), 0 prompts orphan
