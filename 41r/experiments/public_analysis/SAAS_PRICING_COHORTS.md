# 3 SaaS 가격 페이지의 페르소나별 반응 진단 — Notion · Linear · Figma

> **무엇**: PM/디자이너/엔지니어 페르소나 60명(20명 × 3 사이트)이 Notion · Linear · Figma 가격 페이지를 검토하며 어느 플랜을 선택할지 결정하는 시뮬레이션.
> **방법**: 41R Persona Bench (n=200 Upworthy ablation으로 검증된 페르소나 모델, +16%p [9.5, 22.5]%p over baseline).
> **목적**: PM이 가격 페이지를 설계할 때 "어떤 사용자 타입이 어디서 막히는지" 사전 진단.

## TL;DR

| 사이트 | 평균 outcome | 결정에 가장 영향 큰 trait | 핵심 발견 |
|---|---|---|---|
| **Notion** | 0.16 (낮음) | **research_depth -0.58** (압도적) | 리서치 깊이 ↑ → 결정 ↓ — *분석 마비*. 비교 정보 너무 많음 |
| **Linear** | 0.28 | **impulsiveness +0.39** | 충동 ↑ → 결정 ↑ — 첫인상으로 결정. 깊이 비교 안 함 |
| **Figma** | 0.28 | **impulsiveness +0.34, privacy_sensitivity +0.24** | 권한/팀 관리 명확함이 신뢰 신호로 작동 |

세 가격 페이지 모두 **즉시 결제 = 0건/20명**. 모두 "검토(partial)" 또는 "포기(abandoned)". 이는 실제 가격 페이지 funnel 현실(검토 → 후일 결정)과 일치 — AI 페르소나가 결제 환상을 만들지 않는다는 sanity 신호.

---

## 1. Notion 가격 페이지

**URL**: https://www.notion.so/pricing
**페르소나**: 팀 도입 결정자 (PM·PO·팀장, 28~42세, 5~10명 팀)
**Task**: 무료 vs 유료 vs Business 비교 후 어느 플랜이 우리 팀에 맞는지 결정

### 결과 (n=20)

```
결제: 0건
검토 단계 (partial): 9건 (45%)
포기 (abandoned): 11건 (55%)
평균 conversion 확률: 0.16 (stdev 0.19)
```

### Trait → outcome 상관

| Trait | 상관계수 | 해석 |
|---|---|---|
| **research_depth** | **-0.58** | 리서치 깊은 사용자일수록 결정 못 함 |
| tech_literacy | +0.39 | 기술 익숙한 사용자가 더 잘 결정 |
| price_sensitivity | -0.33 | 가격 민감 사용자는 망설임 |
| impulsiveness | +0.32 | 충동적일수록 결정 |

### 진단

**가장 강한 신호 (압도적)**: `research_depth -0.58`.
"플랜을 꼼꼼히 비교하려는 사용자일수록 오히려 결정을 못 함." 이는 전형적인 **분석 마비(analysis paralysis)**. Notion 가격 페이지는 4개 플랜 × 다수 feature 비교표로, 신중한 사용자가 압도되는 구조.

**PM Action 후보**:
- 비교 인지부담 줄이기 (default plan 추천 + "왜 이 플랜인지" 1줄)
- 팀 규모 입력 → 자동 추천 도구
- "Free vs Plus 차이 핵심 3개" 같은 simplified guide 추가

**A/B 테스트 설계 권고**:
> 단일 variant 테스트로 끝나면 안 됨. **research_depth 높은 segment**(꼼꼼한 PM)에서 +효과가 큰 variant와 **impulsive segment**(빠른 결정자)에서 -효과 없는 variant를 별도 검증.

---

## 2. Linear 가격 페이지

**URL**: https://linear.app/pricing
**페르소나**: 엔지니어링 도입 결정자 (테크리드·CTO·매니저, 26~40세, 5~15명 팀)
**Task**: Jira에서 옮길지 검토 중. 5~15명 팀에 적합한지 판단.

### 결과 (n=20)

```
결제: 0건
검토 단계 (partial): 12건 (60%)
포기 (abandoned): 8건 (40%)
평균 conversion 확률: 0.28 (stdev 0.25)
```

### Trait → outcome 상관

| Trait | 상관계수 | 해석 |
|---|---|---|
| **impulsiveness** | **+0.39** | 충동적일수록 결정 |
| research_depth | -0.28 | 리서치 깊을수록 망설임 |
| visual_dependency | -0.12 | 시각 의존도는 큰 영향 없음 |
| privacy_sensitivity | -0.09 | 큰 영향 없음 |

### 진단

**가장 강한 신호**: `impulsiveness +0.39`.
Notion과 정반대 패턴. **Linear 가격 페이지는 "즉시 호감으로 결정"하는 구조**. 깊은 비교 없이 "디자인이 좋고 가격이 합리적"이면 진행. 이는 Linear의 의도된 디자인 철학과 일치 (단순함, 명확성).

**그러나 위험 신호**: 검토 단계(partial) 60%가 가장 높음. 즉 "마음에 들지만 결제 직전에 멈춤"이 가장 흔함. 결제 진입 마찰을 줄이면 conversion ↑ 가능.

**PM Action 후보**:
- "지금 시작" CTA 명확화
- 결제 단계 step 수 줄이기
- 14일 무료 trial 직접 시작 버튼

**A/B 테스트 설계 권고**:
> Linear는 segment 분기가 작음 (impulsiveness 외 약함). **단일 variant A/B로 충분**. CTA 강화 vs 가격 표시 변경 같은 테스트가 적합.

---

## 3. Figma 가격 페이지

**URL**: https://www.figma.com/pricing
**페르소나**: 디자인 도입 결정자 (디자이너·디자인리드·디렉터, 25~40세, 3~8명 팀)
**Task**: Professional vs Organization 중 적합한 플랜 결정.

### 결과 (n=20)

```
결제: 0건
검토 단계 (partial): 17건 (85%)
포기 (abandoned): 3건 (15%)
평균 conversion 확률: 0.28 (stdev 0.14)
```

세 사이트 중 **가장 안정적 패턴** (stdev 가장 낮음). 즉 페르소나별 반응이 비교적 균일 — Figma 가격 페이지는 잘 정리됨.

### Trait → outcome 상관

| Trait | 상관계수 | 해석 |
|---|---|---|
| **impulsiveness** | **+0.34** | 충동적일수록 결정 |
| **privacy_sensitivity** | **+0.24** | 프라이버시 민감 사용자가 오히려 outcome ↑ |
| price_sensitivity | +0.16 | 약한 양의 상관 (특이) |
| visual_dependency | +0.12 | 약함 |

### 진단

**가장 흥미로운 신호**: `privacy_sensitivity +0.24` (양의 상관).
대부분 SaaS에서 프라이버시 민감 사용자는 **부담**(privacy 우려로 가입 망설임)인데, Figma는 반대. 이는 Figma의 **권한/팀 관리 구조 명확화**가 프라이버시 민감 사용자에게 신뢰 신호로 작용한다는 해석.

**PM Action 후보**:
- 권한/team management 섹션 더 명시적으로 (이미 잘 되어 있어서 효과)
- SOC2/SSO 같은 enterprise security 신호 강조
- 가장 안정적인 결과 = 큰 변경 위험. 점진적 최적화가 적합.

**A/B 테스트 설계 권고**:
> stdev 가장 낮음 = segment 분기 작음. **단일 variant 테스트로 충분**. 단, privacy_sensitivity 높은 segment에서는 권한 섹션 강화 variant가 분기 만들 수 있음.

---

## 4. Cross-Site 메타 (9개 사이트 합산)

이번 3개 SaaS + 기존 6개 사이트 (29CM·Class101·오늘의집·Webflow·Glossier·Figma 코호트 1) = 9개 사이트 cross-cohort 분석:

| Trait | 평균 상관 | 9개 사이트 일관성 | 해석 |
|---|---|---|---|
| **impulsiveness** | **+0.248** | **78%** (7+ / 2-) | ✅ 충동성은 outcome 양의 영향 |
| **research_depth** | **-0.236** | **78%** (0+ / 7-) | ✅ 리서치 깊이는 outcome 음의 영향 (분석 마비) |
| **price_sensitivity** | **-0.219** | **78%** (2+ / 7-) | ✅ 가격 민감도는 outcome 음의 영향 |
| privacy_sensitivity | +0.124 | 56% | ⚠️ 사이트 의존적 |
| visual_dependency | -0.052 | 56% | ⚠️ 사이트 의존적 |
| tech_literacy | -0.052 | 44% | ⚠️ 사이트 의존적 |
| social_proof_weight | -0.040 | 44% | ⚠️ 사이트 의존적 |

### 검증된 페르소나 핵심 차원 3가지 (9개 사이트 78% 일관)

1. **충동성 (impulsiveness)** → conversion ↑
2. **리서치 깊이 (research_depth)** → conversion ↓ (분석 마비)
3. **가격 민감도 (price_sensitivity)** → conversion ↓

이 3가지는 사이트 종류와 무관 (이커머스, SaaS, 콘텐츠) — **모든 PM이 가격 페이지 설계 시 고려해야 할 핵심 segment 차원**.

### 사이트 의존적 trait 4가지

privacy, visual, tech_literacy, social_proof는 사이트 카테고리에 따라 영향 방향이 뒤집힘. 이는 41R의 한계가 아니라 **신호** — 이런 trait는 사이트 context와 함께 해석해야 함.

---

## 5. 한계 (정직한 고지)

- **시뮬레이션 결과** (실제 사용자 0명). GA 데이터 cross-check 0건.
- **N=20/사이트**, bootstrap CI 추가 권장.
- **한국 페르소나 풀 (KR-Seoul 기반)**. 국제 일반화 검증 안 됨.
- **text mode 시뮬** (Vision browser 아님). 실제 페이지 렌더링 차이 미반영.
- **41R 모델 자체의 한계**: 절대 수치 GA4 대비 6~21× 과대평가. 본 분석은 **상대 비교만** 유효.

## 6. 재현 방법

```bash
git clone https://github.com/kimtaeyoon83/41r-advisor
cd 41r-advisor/41r
.venv/bin/python3 experiments/public_analysis/run_saas_cohorts.py
.venv/bin/python3 -m modules.cross_cohort_meta
```

전체 reproducible bench: `bench/run_full_eval.sh`.

## 7. 더 깊이

- 방법론 검증: `bench/PAPER_DRAFT.md` — n=200 Upworthy ablation, +16%p [9.5, 22.5]%p
- 코드: https://github.com/kimtaeyoon83/41r-advisor
- 재현: `make verify-all`

---

**작성**: 41R Persona Bench / 2026-04-14
**문의**: GitHub Issues
