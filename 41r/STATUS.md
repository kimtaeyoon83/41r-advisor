# 41R Persona Market — 현재 상태 (2026-04-14)

> **프로젝트 단계**: H1 기술 검증 완료, H1 시장 검증 대기
> **누적 비용**: ~$48 (시스템 개발 + Ablation 2회 + 외부 데이터 통합)
> **GitHub**: https://github.com/kimtaeyoon83/41r-advisor

---

## 한 페이지 요약

**우리가 만든 것**: AI 페르소나가 실제 브라우저에서 사이트를 사용하고, "사람 타입별로 반응이 어떻게 다를지" 진단하는 도구.

**핵심 가치 (통계 입증됨)**: Demographic-only 대비 **분기 탐지 +16%p (p=0.000009, n=200)**.

**판매 메시지**: PM의 변경 아이디어 10개 중, A/B 테스트 전에 "세그먼트별로 갈리는 3개"를 **24시간 · 건당 ~$5**에 식별.

**솔직한 한계**: 절대 수치는 GA 대비 14~19× over-estimate. 실제 고객 유료 전환 0건. 시장 검증은 이제부터.

---

## 1. 가설 검증 상태

### H1 시장 가설 (v2, 피벗 후)
> CPO/Head of Growth는 A/B 테스트 설계 전 단계의 "세그먼트 분기 진단"에 건당 ~$5 수준 예산을 낼 의향이 있다.

**검증 상태**: ❌ 아직 0건 (발송 전)

**Kill Criteria (단계화)**:
| 단계 | 지표 | Kill | Pass |
|---|---|---|---|
| 1 | 발송→응답 | <3/30 | ≥5 |
| 2 | 응답→샘플 요청 | 0/5 | **≥3** |
| 3 | 샘플→미팅 | 0/3 | ≥2 |
| 4 | 미팅→의향 | 0/2 | ≥1 |
| 5 | 의향→결제 | $5+ 0건 | 1건+ |

### H1.1 제품 가치 (marginal value)
> 41R의 개인 성향 프로필이 demographic-only baseline 대비 marginal value를 제공한다.

**검증 상태**: ✅ **n=200 통계적 입증**
- 세그먼트 분기 탐지: 42.5% → 58.5% (+16%p, p=0.000009)
- 정확도: 무의미한 차이 (55% vs 61%, p=0.073) — "정답 맞추기"가 아닌 "분기 탐지"가 가치

### H1.2 행동 벤치마크 일치
> 41R 페르소나가 NNGroup·Baymard 등 연구와 일치한다.

**검증 상태**: ✅ **6/6 일치** (5 일치 + 1 부분 일치)

### H1.3 A/B 예측 정확도
**검증 상태**: ⚠️ 부분 입증 — 55~83% (n에 따라), 승자 예측은 Demo와 유의한 차이 없음

---

## 2. 시스템 상태

### 모듈 (M1~M7 + 코호트)
- M1 Persona Store · M2 Browser Runner · M3 Agent Loop · M4 Provenance(stub) · M5 Report Generator · M6 Review Agent · M7 Version Manager
- **Cohort System**: persona_generator (Latin Hypercube), cohort_runner (multiprocessing), cohort_report (Wilson CI + 상관 분석)
- **Hallucination Guard**: 출처 추적 + claim 태깅 + p-value 자동 재계산
- **Benchmark Loader**: GA4 + Open Bandit baseline 자동 비교

### 품질
- **49 unit tests** 통과 (pytest)
- **Makefile + pre-commit hook + GitHub Actions CI**
- 핵심 모듈 coverage: version_manager 86%, persona_store 71%, cohort_report 55%, hallucination_guard 51%

### 페르소나 풀 (15명)
- **기본 5명** (수동): 충동형·신중형·가격민감·실용주의·시니어
- **확장 5명** (수동): B2B 구매자, Z세대, 워킹맘, 크리에이터, 해외 한국인
- **Demo baseline 5명**: nnage/gender/job만
- **자동 생성기**: 세그먼트 사양 입력 → N명 생성

---

## 3. 외부 데이터 통합 (Tier 1 상업 가능)

| 데이터셋 | 용도 | 주요 수치 |
|---|---|---|
| **NNGroup·Baymard·Think with Google** | 벤치마크 일치 확인 | 6/6 일치 |
| **Upworthy Archive** (14MB, 4,873 test) | A/B 예측 검증 | 200건 sampling, 분기 탐지 +16%p |
| **GA4 Sample** (BigQuery) | 절대 수치 reality check | 실제 전환율 1.65%, 장바구니 4.7% |
| **Open Bandit** (ZOZOTOWN) | CTR sanity check | 실제 평균 CTR 0.38% |

### Reality Check 결과
| 지표 | 41R 예측 | 실제 (GA4) | Gap |
|---|---|---|---|
| 장바구니 도달률 | 30% | 2.16% | 14× over |
| 평균 페이지뷰 | 9.1 | 3.74 | 2.4× over |
| 광고 CTR | 30% | 0.38% | 80× over |

→ **결론**: 절대 수치 신뢰 불가, **상대 비교만 사용**.

---

## 4. 생성된 자료

### 리포트 (사업팀/고객 공유용)
| 파일 | 타겟 | 크기 |
|---|---|---|
| `reports/EXECUTIVE_REPORT.html` | **사업팀/CPO** — 가설→방법→결과→한계 9개 섹션 | 32KB |
| `reports/SIMPLE_REPORT.html` | **일반인/투자자** — 비유 최소, 담담한 설명 | 21KB |
| `reports/sample_report_v2.html` | 사업팀 — 종합 진단 + Reality Check | 32KB |
| `reports/index.html` | 모든 리포트 인덱스 대시보드 | 14KB |

### 5개 타겟 사이트 코호트 진단 (Appendix)
- 29CM, 클래스101, 오늘의집, Webflow, Glossier
- ⚠️ text mode 시뮬 (실측 cross-check 0건) — 가설 수준

### 검증 문서
| 문서 | 내용 |
|---|---|
| `experiments/ablation/MARGINAL_VALUE_REPORT.md` | Ablation n=12 + n=200 |
| `experiments/ab_validation/VALIDATION_REPORT.md` | A/B 역검증 |
| `experiments/ab_results/persona_ground_truth_validation.md` | NNGroup 대조 |
| `experiments/browser_mode_validation.md` | Browser 안정성 테스트 |
| `experiments/datasets/open_bandit/SANITY_CHECK.md` | 절대 수치 교차 확인 |
| `experiments/constitution_notes/external_benchmarks.md` | 데이터셋 라이선스 거버넌스 |

### 아웃바운드 자료 (발송 대기)
| 자료 | 위치 |
|---|---|
| CPO 타겟 리스트 30곳 | `experiments/outbound/cpo_target_list.md` |
| 담당자 매핑 가이드 | `experiments/outbound/contact_mapping_guide.md` |
| 이메일 템플릿 3종 | `experiments/outbound/cold_email_template.md` |
| 사이트별 맞춤 이메일 5건 | `experiments/outbound/personalized_emails.md` |
| 차별점 문서 | `experiments/outbound/differentiation.md` |

### 법률 준비
- `experiments/legal_review/H6_legal_questions.md` — 7개 영역 질문 (FTC synthetic reviews, k-anonymity, 데이터셋 라이선스 등)

---

## 5. 커밋 히스토리 (이 세션)

| 커밋 | 주요 변경 |
|---|---|
| `85fdb4e` | Initial commit — 시스템 + 페르소나 + 기존 5 사이트 코호트 |
| `26d1a63` | Phase L — 외부 데이터셋 + n=200 ablation 통계 입증 |
| `4d5dedf` | H1 가설 피벗 v2 (외부 피드백 반영) |
| `7414a8a` | SIMPLE_REPORT 초안 (마케팅톤 과다) |
| `3f6e06d` | SIMPLE_REPORT 재작성 (담담한 톤) |
| `63887ca` | SIMPLE_REPORT 외부 데이터 검증 상세화 |
| `5f7956e` | SIMPLE_REPORT 외부 데이터 실제 샘플 추가 |

---

## 6. 영역별 품질 등급 (현재)

| 영역 | 등급 | 비고 |
|---|---|---|
| 시스템 인프라 | A | Makefile + CI + claim 태깅 + monitoring |
| 리포트 품질 | A | 출처 추적 + 49 숫자 검증 + hallucination guard |
| 코드 테스트 | A | 49 tests, 핵심 모듈 71~86% coverage |
| 검증 엄밀성 | **B+** → **A−** | n=200으로 marginal value 입증 (p<0.001) |
| 데이터 신뢰도 | B | Browser 검증 + 외부 cross-check (GA4/Open Bandit) |
| **시장 증명** | **F** | **발송 0건 — 사용자 결정 대기** |

**평균: B+~A−** (5개 영역 A/A−, 시장 증명만 F)

---

## 7. 남은 작업 (사용자 결정 필요)

### 🔴 우선순위 높음 (F1: 시장 검증)
1. **EXECUTIVE_REPORT 사업팀 공유** → 포지셔닝 피드백
2. **CPO 30명 중 1차 5~10명 발송** 결정
   - 담당자 매핑 가이드 따라 LinkedIn/Apollo 활용
   - 사이트별 맞춤 이메일 5건 준비됨
3. **응답률 추적** (2주) → 단계별 Kill 임계 체크

### 🟡 우선순위 중간 (F2: 데이터 cross-check)
- NDA 가능 파트너사 1곳 확보 → 실제 GA/Hotjar와 41R 예측 대조
- H2 진입 결정 데이터

### 🟢 우선순위 낮음 (H6: 법률)
- 우선 질문 2개 (FTC synthetic reviews + 정확도 주장 면책)
- 예상 비용 50~100만원

---

## 8. 의사결정 트리

```
F1 발송 (5~10명)
  ├─ 응답 < 3/30 → 메시징 재설계 후 재시도
  ├─ 응답 3~5 + 샘플 요청 0 → 가치 제안 재설계
  ├─ 샘플 요청 ≥ 3 + 미팅 ≥ 2 + 의향 1건+ → ✅ H2 진입 (정확도 검증)
  └─ 미팅 0 + 의향 0 → ❌ H1 kill or 피봇
```

---

## 연락 / 자료 접근

- **GitHub**: https://github.com/kimtaeyoon83/41r-advisor
- **시작점**: `reports/index.html` (전체 인덱스)
- **사업팀용**: `reports/EXECUTIVE_REPORT.html`
- **일반인용**: `reports/SIMPLE_REPORT.html`

검증 재현:
```bash
cd 41r
make test              # 49 tests
make audit             # 리포트 hallucination 검증
.venv/bin/python3 experiments/ablation/run_ablation_n200.py  # Ablation 재실행
```
