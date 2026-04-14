# External Benchmark Datasets — 거버넌스

> **목적**: 41R 검증에 사용하는 외부 공개 데이터셋의 메타정보, 라이선스, 활용 시나리오 명시 관리
> **규칙**: append-only. 새 데이터셋 추가 시 아래 표 + 상세 섹션 추가
> **상태**: v1 (2026-04-14)

---

## 사용 정책 매트릭스

| Tier | 라이선스 유형 | 사용 가능 범위 |
|---|---|---|
| **상업 OK** | CC BY 4.0, CC0, MIT, Apache 2.0 | 아웃바운드 자료, 고객 리포트, 외부 발표 모두 가능 |
| **연구 전용** | CC BY-NC-SA, Research only, Kaggle competition rules | 내부 R&D, 학술 발표만. 상업 자료 인용 금지 |
| **참고만** | 무료 열람만, 다운로드 불가 | 메타데이터/캡쳐 reference만, 데이터 자체 미통합 |

---

## 통합 데이터셋 목록 (v1)

| # | 이름 | Tier | 갭 | 통합 상태 |
|---|---|---|---|---|
| 1 | Upworthy Research Archive | **상업 OK** | A/B 검증 (n 확장) | ✅ **통합 완료** (n=200 ablation) |
| 2 | GA4 Sample (BigQuery) | **상업 OK** | 인구통계 × 행동 baseline | ⏳ L3 진행 예정 |
| 3 | Open Bandit Dataset (ZOZO) | **상업 OK** | A/B lift 분포 sanity | ⏳ L4 진행 예정 |

---

## 1. Upworthy Research Archive

- **출처**: OSF.io node `jd64p` (https://osf.io/jd64p/)
- **다운로드**: 4개 CSV 파일 (총 128MB)
  - `upworthy-archive-exploratory-packages-03.12.2020.csv` (14.3MB, 4,873 tests) ← **사용 중**
  - `upworthy-archive-confirmatory-packages-03.12.2020.csv` (66.5MB, 22,743 tests)
  - `upworthy-archive-holdout-packages-03.12.2020.csv` (14.2MB)
  - `upworthy-archive-undeployed-packages.01.12.2021.csv` (33.2MB)
- **라이선스**: **CC BY 4.0** — 상업 이용 가능, Cornell/MIT 출처 표기 필요
- **인용 형식**: Matias et al. (2021), Nature Scientific Data
- **데이터 schema**:
  ```
  clickability_test_id, headline, lede, excerpt, impressions, clicks, winner, first_place, ...
  ```
- **41R 활용**:
  - 4,873 exploratory tests에서 (multi-variant + impressions ≥1000 + lift ≥10%) 필터로 4,764건 추출
  - 그 중 200건 random sampling (seed=42), 50% 라벨 셔플
  - Demo-only vs 41R ablation의 통계 power 확보 (n=12 → 200)
- **한계**:
  - 도메인이 헤드라인 (이커머스 X)
  - segment-level breakdown 없음 (age/gender 미기록)
  - 2014~2015년 데이터 (모바일 SNS 시대 이전 일부)
- **저장 위치**: `experiments/datasets/upworthy/`
- **전처리 스크립트**: `experiments/datasets/upworthy/`에 inline (raw → ablation_cases_n200.json)
- **확장 가능**: confirmatory CSV (22,743건)으로 n=1000+ 확장 가능

## 2. GA4 Sample Dataset (Google Merchandise Store)

- **출처**: BigQuery `bigquery-public-data.ga4_obfuscated_sample_ecommerce`
- **문서**: https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset
- **라이선스**: Google Cloud Public Datasets — 상업 분석 가능 (obfuscated)
- **접근 방법**: BigQuery 무료 sandbox (1TB/월), GCP 계정 필요
- **데이터 범위**: 2020-11-01 ~ 2021-01-31 (3개월)
- **41R 활용** (예정):
  - device_category (mobile/desktop/tablet) × event sequence × conversion rate breakdown
  - country × user_type (new/returning) 세그먼트별 전환율
  - 우리 페르소나 분포 grounding (예: "20대 모바일 신규 = 약 X%"의 ground truth)
- **한계**:
  - 단일 사이트 (Google Store) — 일반화 제한
  - obfuscated (일부 필드 NULL/<Other>)
  - 3개월만
- **통합 상태**: L3에서 SQL 쿼리 작성 예정

## 3. Open Bandit Dataset (ZOZOTOWN)

- **출처**: ZOZO Research https://research.zozo.com/data.html, GitHub https://github.com/st-tech/zr-obp
- **라이선스**: **CC BY 4.0** — 논문/GitHub 명시
- **인용 형식**: Saito et al. (2020), arXiv 2008.07146
- **다운로드**: 공식 페이지 zip + `pip install obp` Python SDK
- **데이터 규모**: 26M rows, 7일 실험, 3 campaigns × 2 policies (Bernoulli TS vs Random)
- **schema**: timestamp, item_id, position, click, propensity_score, user_features, item_context
- **41R 활용** (예정):
  - 진짜 A/B 테스트의 lift 분포 → 우리 41R 예측 lift가 현실적 범위(0.5~5%)인지 sanity check
  - Men's/Women's/All 캠페인별 정책 차이 → 페르소나 segment 차이 grounding
- **한계**:
  - 2019 일본 패션 (한국 X)
  - UI A/B가 아닌 추천 정책 A/B
- **통합 상태**: L4에서 분석 예정

---

## 사용 안 함 / 보류 데이터셋

다음은 리서치 결과 검토 후 통합 보류 결정:

| 이름 | 보류 사유 |
|---|---|
| RetailRocket | CC BY-NC-SA → 상업 자료 인용 금지. R&D 전용 |
| Coveo SIGIR 2021 | Research only + 등록 폼 필요 |
| H&M Kaggle | Competition rules, segment 정보 일부만 |
| Criteo Uplift | NC-SA + 피처 익명 (해석 어려움) |
| Yahoo R6A | 신청 절차 + 학술 전용 |
| GoodUI | 다운로드 불가 (열람만), ToS 위반 위험 |
| Pew Research | SPSS format + 자기보고 (행동 데이터 X) |
| EOTT Eye Tracking | n=51 너무 작음 |
| NNGroup, Baymard | raw data 비공개, reference만 사용 |

---

## 추가 시 절차

1. **라이선스 확인 우선** — CC BY-NC-SA는 상업 자료 인용 금지
2. **데이터 출처 표기** — 모든 사용 시 원본 인용
3. **전처리 스크립트 commit** — 재현 가능성 보장
4. **이 문서에 entry 추가** (append-only)
5. **lineage.json에 데이터셋 hash 기록** (검증 시)

## H6 법률 자문 연관

상업 vs 연구용 라이선스 차이가 H1 아웃바운드와 직결:
- "Upworthy 데이터로 검증" → 안전 (CC BY 4.0)
- "RetailRocket 데이터로 검증" → 위험 (NC = non-commercial)

H6 자문 시 "외부 데이터셋 라이선스 인용 책임 범위" 추가 질문 권장.
