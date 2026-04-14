# 페르소나 상황-반응 테스트 프레임워크 (Situation-Response Test)

> **버전**: v1.0
> **작성일**: 2026-04-13
> **용도**: 새 페르소나 추가 또는 soul 변경 시 회귀 검증

---

## 테스트 구조

### Part A: 방향성 테스트 (Directional)
- 대량 테스트에서 의미 있는 세그먼트 간 차이 확인
- "충동형이 신중형보다 빠른가?" 수준의 방향성 검증
- 통과 기준: 70% 이상

### Part B: 세밀한 검증 (Granular)
- 특정 상황에서 올바른 구체적 반응 확인
- "쿠키 모달에서 충동형은 수락, 신중형은 거부하는가?" 수준
- 잘못된 행동을 잡아내는 데 초점
- 통과 기준: 개별 pass/fail

---

## Part A: 방향성 테스트 (8개)

| 코드 | 테스트 | 예측 | 근거 |
|---|---|---|---|
| A1 | CTA 클릭까지 턴 수 | 충동 < 신중 | NNGroup 10~20초 결정 |
| A2 | 시각자극 부족 시 이탈 속도 | 충동이 더 빠름 | Baymard 22% 마찰 이탈 |
| A3 | read() 비율 | 충동 < 신중 | NNGroup 20~28% 읽음 |
| A4 | 신뢰 탐색 행동 유무 | 신중만 함 | Baymard 25% 신뢰 이탈 |
| A5 | 가격 발견 후 행동 | 충동=즉시결정, 신중=추가탐색 | Think w/ Google Messy Middle |
| A6 | 스크롤 깊이 | 신중 > 충동 | NNGroup F-pattern |
| A7 | 감정 톤 | 충동=조급/부정, 신중=차분/집중 | 페르소나 정의 |
| A8 | 종료 방식 | 충동=빠른이탈, 신중=max_turns | Baymard 59% 둘러보기 |

## Part B: 세밀한 검증 (10개)

| 코드 | 상황 | 충동형 예측 | 신중형 예측 | 근거 |
|---|---|---|---|---|
| G1 | 쿠키 모달 | 즉시 수락 | 거부/읽기 | privacy_sensitivity |
| G2 | CAPTCHA 발생 | 1~2턴 내 이탈 | — | patience 2초, F010 |
| G3 | 푸터/정책 정보 | 안 감 | 반드시 확인 | trust_signals |
| G4 | 시각 트리거 없는 사이트 | read 없이 이탈 | 읽은 후 판단 | visual_dependency |
| G5 | 가격 비교 (연간/월간) | 안 비교 | 반드시 비교 | research_depth |
| G6 | 가격 페이지 | 5턴 내 결정 | 10턴도 부족 | decision_speed |
| G7 | 고객 사례/GMV | 안 봄 | 반드시 확인 | social_proof_weight |
| G8 | 시각적 강조 요소 | 즉시 반응 | 읽은 후 반응 | visual_dependency |
| G9 | FAQ | 안 봄 | 2개+ 확인 | research_depth |
| G10 | CTA 시각적 판단 | 색상/위치로 클릭 | 텍스트 읽고 클릭 | decision_speed |

---

## 실행 방법

```bash
# 1. 세션 실행
python3 scripts/run_golden_sessions.py

# 2. 테스트 채점 (자동)
python3 scripts/run_persona_tests.py

# 3. 결과 확인
cat experiments/ab_results/test_results_latest.json
```

## 채점 기준

- Part A: 방향성 일치 = 100점, 불일치 = 0점
- Part B: pass = 100점, fail = 0점
- 종합: (A 평균 + B 평균) / 2

## 등급

| 점수 | 등급 | 의미 |
|---|---|---|
| 80%+ | A | 프로덕션 사용 가능 |
| 60~79% | B | 방향성 일치, 세부 개선 필요 |
| 40~59% | C | 부분 일치, soul/프롬프트 수정 필요 |
| 40% 미만 | D | 재설계 필요 |

## 한계

1. 6세션은 통계적 유의성 부족 (최소 30+)
2. 방향성 테스트는 "LLM이 지시대로 연기하는가"를 측정하는 것
3. 정량적 정확도(전환율 예측)는 별도 검증 필요 (H2)
4. 벤치마크 수치의 원본 확인 필요
