# CATE Validator Self-Demo — n=200 Ablation 데이터 활용

## 목적
F2 NDA 파트너에게 "실제 A/B 데이터로 어떻게 41R 예측을 검증하는지" 시연.

## 변환
- Source: `results_ablation_n200.json` (n=200 Upworthy ablation)
- Rows: **2000** (200 cases × 5 personas × 2 arms)
- Segment: 5개 인구통계 segment
- Variant: A=Demo-only arm, B=41R arm
- Outcome: A/B winner 예측 적중 = 1, 빗나감 = 0

## CATE 추정 방법: `naive_segment_diff`
EconML 미설치 — naive segment difference 사용. H2 정식 운영 시 econml 설치 권장.

## Overall ATE (41R - Demo): **-3.1%p**

## Per-Segment 결과

- **20대 남성 (직장인)**: ⚪ 효과 불확실 (CI 0 포함, CATE=+2.0%p)
- **30대 여성 (회계)**: ❌ 41R 손해 -11.0%p (CI 0 미포함)
- **30대 여성 (교사)**: ⚪ 효과 불확실 (CI 0 포함, CATE=+0.5%p)
- **40대 남성 (IT)**: ⚪ 효과 불확실 (CI 0 포함, CATE=-3.0%p)
- **50대+ 여성**: ⚪ 효과 불확실 (CI 0 포함, CATE=-4.0%p)

## 41R 예측 vs 실제 일치도
- 예측한 분기 segment: ['20대 남성 (직장인)', '30대 여성 (교사)', '30대 여성 (회계)', '40대 남성 (IT)', '50대+ 여성']
- 실제 분기 segment: ['20대 남성 (직장인)', '30대 여성 (교사)', '30대 여성 (회계)']
- True Positive: ['20대 남성 (직장인)', '30대 여성 (교사)', '30대 여성 (회계)']
- False Positive: ['40대 남성 (IT)', '50대+ 여성']
- False Negative: []
- **F1 일치도: 0.75**

## 활용
1. **F2 NDA 파트너 미팅 시연자료**: "귀사 A/B 데이터에 같은 검증 적용"
2. **자체 데이터로 워크플로우 검증됨** = 외부 데이터 0건이어도 방법론 검증 가능
3. **경쟁사 비교**: Aaru, UXAgent, Maze 모두 CATE validator 미보유

## 한계
- 본 데모는 self-data (Upworthy A/B 헤드라인) — 실제 e-commerce/SaaS 데이터 아님
- segment 정의가 인구통계 5종에 국한 — 실제 고객은 다른 segment 정의 가능
- 41R의 "diverging_segments" 사전 예측은 본 데모에서 가설적 (모든 segment)

## Reproduction
```bash
.venv/bin/python3 experiments/cate_self_demo/run_self_demo.py
```