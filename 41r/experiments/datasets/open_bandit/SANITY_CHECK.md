# Open Bandit Dataset — 41R 예측 Sanity Check

> **데이터셋**: ZOZOTOWN Random policy, ALL campaign sample (10,000 rows, 80 items)
> **원본**: https://research.zozo.com/data.html (CC BY 4.0)
> **인용**: Saito et al. (2020), arXiv 2008.07146

## Open Bandit이 알려주는 현실

| 메트릭 | 값 | 41R 시뮬과 차이 |
|---|---|---|
| **전체 CTR** | **0.38%** (10K 노출 중 38회 클릭) | 41R "30% 전환" 예측 대비 **80배 낮음** |
| 최고 CTR item | 2.63% | 가장 높아도 5% 미만 |
| Position 1 CTR | 0.391% | - |
| Position 2 CTR | 0.410% | **2번이 1번보다 높음 (반직관)** |
| Position 3 CTR | 0.337% | - |

## 41R 예측 vs 실제 — 큰 갭

### 우리가 예측한 "30% 전환율" (29CM 코호트)
- 5명 페르소나 중 6/20 (30%)이 장바구니 도달
- → 의미: "이 사이트의 30%의 유저가 장바구니 담는다"

### 실제 e-commerce 데이터
- 추천 클릭률 **0.38%**
- 페이지뷰 → 장바구니 일반적으로 **2~5%**
- 장바구니 → 결제 일반적으로 **20~30%**
- **실제 PV → 결제 전환율 0.4~1.5%** 보편적

## 진단

**41R 예측은 절대 수치로 신뢰 불가.** 다음 갭 확인:

1. **시뮬 outcome 정의가 너무 관대**:
   - "장바구니 담기 직전"도 partial 처리 → 인플레이션
   - 실제 GA에서는 결제 완료만 transaction count

2. **페르소나 표본의 conversion bias**:
   - 5명 모두 "쇼핑 의도가 있는" 가정으로 simulate
   - 실제 트래픽은 70~90%가 그냥 둘러보는 유저 (no intent)

3. **세션 길이 왜곡**:
   - LLM이 생성한 평균 9턴 = 매우 high engagement
   - 실제 평균 페이지뷰 (이커머스) 3~5 페이지

## 권고 사항 — 41R 리포트 표현 수정

❌ "29CM 전환율 30%로 예측" (절대 수치 주장)
✅ "29CM 시뮬에서 30% 페르소나가 장바구니에 도달 — 단, 이는 'shopping intent 있음' 가정 코호트의 상대 비교용. 실제 사이트 전환율은 별도 데이터 필요"

❌ "Webflow 이탈률 50%"
✅ "Webflow 시뮬에서 50% 페르소나가 결제 단계 도달 못함 — segment 분기 신호"

## Sanity Check Threshold

41R 예측 검증 시 다음 확인:

| 41R 예측 | 현실적인가? | 액션 |
|---|---|---|
| 절대 전환율 > 10% | ❌ 비현실적 | "코호트 내 비율"로만 표현 |
| 절대 전환율 1~10% | ⚠️ shopping intent 가정 코호트 한정 | 명시적 가정 표기 |
| 절대 전환율 < 1% | ✅ 현실적 (e-commerce 평균) | 직접 사용 OK |
| Lift 추정 (vs control) | △ 케이스마다 다름 | Open Bandit/Upworthy로 sanity check |
| Position effect | 1>2>3 가정 | **틀릴 수 있음** (Open Bandit은 2가 가장 높음) |

## 다음 액션

1. **sample_report_v2.html에 "절대 vs 상대 수치" disclaimer 추가**
2. **cohort_report.py에 Open Bandit 기준선 비교 추가** ("우리 mean 30% vs 실제 e-commerce 0.4~1.5%")
3. **페르소나 voice에 "shopping intent 있음" 가정 명시**

## 한계

- ZOZOTOWN 일본 패션 — 한국 사이트와 직접 비교 어려움
- 추천 클릭률 ≠ PDP→checkout 전환율 (다른 metric)
- 2019 데이터 (mobile 비중, AI 추천 등 변화 반영 안 됨)
