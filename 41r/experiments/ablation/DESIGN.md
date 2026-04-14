# Ablation Study — 개인 페르소나 프로필의 Marginal Value 검증

> **작성일**: 2026-04-14
> **목적**: 41R의 핵심 차별점인 "개인 성향 프로필"이 demographic-only baseline 대비 추가 가치를 제공하는지 검증
> **상태**: 설계 확정, 실행 대기

---

## 배경

### 기존 검증 상태 (외부 프로젝트에서 입증됨)
인구통계 기반 대량 에이전트 설문(demographic-only LLM persona)은 이미 유효성이 검증됨:
- 나이 + 성별 + 지역 + 직업 조합만으로도 실제 유저 행동의 통계적 패턴 재현 가능
- CPO/PM 의사결정에 실용적 정보 제공 가능

### 41R이 증명해야 할 가설
인구통계 위에 **개인 성향 프로필**(impulsiveness, research_depth, privacy_sensitivity, trust_signals, frustration_triggers 등)을 추가하면 **marginal value**가 있다.

**없으면**: 41R은 기존 demographic survey 도구 대비 차별점 없음 → 피봇 필요
**있으면**: 41R의 "5개 성향 축 + 좌절 트리거 + 신뢰 기준" 구조가 정당화됨

---

## 실험 설계

### 독립 변수 (Arm)

| Arm | 이름 | 페르소나 구성 |
|---|---|---|
| **A** | Demo-only Baseline | 나이, 성별, 지역, 직업만 |
| **B** | Demo + Persona (41R) | A + 성향 프로필(5축) + 좌절 트리거 + 신뢰 기준 + 내러티브 |

### 통제 조건 (Control)

모든 조건 동일:
- 동일 LLM (Claude Sonnet 4.6, MID tier)
- 동일 프롬프트 구조 (EVALUATION_SYSTEM)
- 동일 테스트 케이스 (12건 공개 A/B, `cases.json`)
- 동일 seed (42) → 라벨 셔플 재현
- 동일 코호트 크기 (arm당 5 페르소나)
- 동일 LLM call 파라미터 (max_tokens, temperature)
- `cache_disabled()` 명시

### 종속 변수 (Metrics)

| # | 메트릭 | 측정 방법 | "B가 낫다"의 증거 |
|---|---|---|---|
| **1** | A/B 승자 예측 정확도 | 12건 중 맞춘 건수 | B_정확도 > A_정확도 |
| **2** | 세그먼트 분기 감지율 | 페르소나 간 의견 분기가 발생한 케이스 비율 | B_분기율 > A_분기율 |
| **3** | 이탈/예측 이유 구체성 | 제3자 LLM(blinded) 점수 1~5 | B_평균 > A_평균 |
| **4** | 행동 variance | 페르소나별 예측 분포 표준편차/엔트로피 | B_variance > A_variance (획일화 방지) |
| **5** | 반직관적 케이스 탐지 | Groove·EA 같은 세그먼트 의견 분기 명확성 | B가 더 명확하게 분기 탐지 |

---

## 통계적 엄밀성

### 유의성 검증
- **메트릭 1, 2, 5**: Fisher's Exact Test (이진 결과, n=12)
- **메트릭 3, 4**: Paired t-test 또는 Wilcoxon signed-rank (paired samples)
- **α = 0.05**

### 샘플 크기 한계 명시
- n=12 케이스로는 통계적 유의성 주장 어려움 (95% CI 광범위)
- 본 실험은 **방향성 검증** (exploratory) — 확정적 결론은 n≥30 케이스로 추후 확장

### 데이터 오염 통제 (v3과 동일)
- 라벨 셔플 (seed=42)
- 회사명 제거
- 시스템 프롬프트에 "사전 지식 사용 금지" 명시

---

## 성공/실패 기준

### 성공 (41R 가치 증명)
- 메트릭 3개 이상에서 B > A (구체성 + 정확도 + 세그먼트 분기)
- 특히 메트릭 #3(구체성)과 #5(반직관적)에서 우위 확인

### 부분 성공 (포지셔닝 재조정)
- 메트릭 1~2개만 우위
- 예: 정확도는 같지만 구체성 우위 → "페르소나는 인사이트 품질 개선 도구"로 포지셔닝

### 실패 (kill signal)
- 모든 메트릭에서 차이 없음 또는 B가 열세
- **액션**: 개인 페르소나 축 제거, demo-only로 피봇. Constitution §12에 추가.

---

## 예상 결과 시나리오

### 시나리오 1: 강한 우위 (most likely)
- 메트릭 3 (구체성): B 우위 (성향 트리거가 구체적 이탈 이유 생성)
- 메트릭 4 (variance): B 우위 (개인 차이로 행동 다양화)
- 메트릭 1 (정확도): 비슷하거나 약간 B 우위
- **해석**: 41R은 "정답 찾기"보다 "이유 설명"에 강함

### 시나리오 2: 약한 우위
- 메트릭 3만 우위
- 메트릭 1, 2, 5는 비슷
- **해석**: 성향 프로필이 정확도 개선엔 기여 안 하지만 설명력은 개선. 리포트 품질 관점으로 포지셔닝.

### 시나리오 3: 혼합
- B가 반직관적 케이스에선 우위, 직관적 케이스에선 열세
- **해석**: "복잡한 세그먼트 분기 필요할 때"만 41R 추천

### 시나리오 4: 차이 없음 (worst case)
- 모든 메트릭 동등
- **해석**: 개인 페르소나가 기여 없음. 피봇 필요.

---

## 실험 절차

1. **Demo-only 페르소나 5개 생성** — 성향 축 제거, 나이/성별/지역/직업만
2. **run_ablation.py 작성** — 2-arm 실행기
3. **실행** — 12 × 2 × 5 = 120 LLM 콜 (약 15~20분, $2~3)
4. **메트릭 계산** — 자동/수동 혼합
5. **MARGINAL_VALUE_REPORT.md 작성** — 결과 + 해석 + 다음 단계

---

## 산출물

- `personas/demo_*/soul/v001.md` × 5
- `experiments/ablation/run_ablation.py`
- `experiments/ablation/results_ablation.json`
- `experiments/ablation/compute_metrics.py`
- `experiments/ablation/blinded_scoring.py`
- `experiments/ablation/MARGINAL_VALUE_REPORT.md`

---

## 한계 및 유의점

1. **n=12 케이스의 통계적 제한** — 본 실험은 방향성 확인이며, 확정 결론은 확장 실험 필요
2. **텍스트 기반 평가** — 실제 브라우저 세션 아님. Ablation 용도로는 충분하나 v3 역검증 대비 정보량 적음
3. **단일 LLM (Sonnet)** — 다른 LLM에서 결과 재현성은 별도 검증 필요
4. **Baseline의 완성도** — Demo-only 페르소나를 얼마나 "공정하게" 구성하느냐에 따라 결과 편향 가능. 본 설계는 실제 논문·설문 문헌에서 사용되는 최소 정보만 포함.
