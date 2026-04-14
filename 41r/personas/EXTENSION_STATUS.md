# Persona Pool — Extension Status

> 페르소나 활용 상태 정리 (orphan 검출 결과 반영, 2026-04-14).

## 활용 중 ✅ — Ablation + 코호트 둘 다 사용

| ID | 사용처 |
|---|---|
| `p_impulsive` | n=200 ablation Arm B, manual cohort |
| `p_cautious` | n=200 ablation Arm B, manual cohort |
| `p_budget` | n=200 ablation Arm B, manual cohort |
| `p_pragmatic` | n=200 ablation Arm B, manual cohort |
| `p_senior` | n=200 ablation Arm B, manual cohort |
| `demo_young_m` | n=200 ablation Arm A (Demo-only baseline) |
| `demo_adult_f` | n=200 ablation Arm A |
| `demo_adult_f2` | n=200 ablation Arm A |
| `demo_adult_m` | n=200 ablation Arm A |
| `demo_senior_f` | n=200 ablation Arm A |

## 정의 후 미사용 ⏳ — H2 예정 (확장 5명)

이 5명은 v002 soul 정의는 됐지만 ablation/코호트에 한 번도 사용되지 않음.
H2에서 NDA 파트너 사이트 특성에 맞춰 활성화 예정.

| ID | 정의 | 활성화 트리거 |
|---|---|---|
| `p_b2b_buyer` | B2B 구매자 (구매팀, 평가위, 의사결정 권한) | F2 NDA 파트너가 B2B SaaS인 경우 |
| `p_genz_mobile` | Z세대 모바일 우선 (16~24세) | F2 NDA 파트너가 Z세대 타겟인 경우 |
| `p_parent_family` | 워킹맘/부모 (가족 결정) | F2 NDA 파트너가 family-oriented 제품인 경우 |
| `p_creator_freelancer` | 크리에이터/프리랜서 (수익화) | F2 NDA 파트너가 creator economy인 경우 |
| `p_overseas_kor` | 해외 한국인 (직구, 환율) | F2 NDA 파트너가 cross-border commerce인 경우 |

**의도된 미사용 이유**: 코호트 간 비교 가능성을 유지하기 위해 ablation/cross-cohort 분석에서는 일관된 5+5 페르소나 풀 사용. 확장 페르소나는 use-case-specific 분석 시 옵션.

## 자동 생성 (Latin Hypercube) ✅

`modules.persona_generator.generate_cohort(spec)` — 코호트별로 자동 생성.

생성된 코호트:
- `cohort_20260414_111133_d3d217` (Notion, n=20)
- `cohort_20260414_111250_6cc9ce` (Linear, n=20)
- `cohort_20260414_111402_cc199e` (Figma, n=20)
- 6개 기존 사이트 코호트

자동 생성 페르소나는 cohort/ 하위 디렉토리에 격리됨. 기본 풀(15명)과 분리됨.

## 정책

- **15명 풀**: 안정 — 변경 시 ablation 재실행 필요
- **확장 5명**: 정의만 유지, F2 트리거 시 활성화
- **자동 생성**: 코호트별 동적 생성, 격리 보존
