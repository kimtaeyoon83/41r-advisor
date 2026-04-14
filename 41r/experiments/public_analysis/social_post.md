# Social Post Drafts — SaaS Pricing Cohort Analysis

> 발행 전 검토용 초안. 게시 채널·타이밍은 사용자 결정.
> AI-generated synthetic research disclosure 포함 (FTC + EU AI Act 대응).

---

## A. LinkedIn 버전 (긴 글, ~250 단어)

**제목**: Notion · Linear · Figma 가격 페이지를 60명의 AI 페르소나가 검토했더니 발견한 패턴

PM·디자이너·엔지니어 페르소나 60명(20명 × 3 사이트)에게 SaaS 가격 페이지를 검토하게 했습니다. AI 시뮬레이션이지만 n=200 검증된 모델 (+16%p over demographic baseline, McNemar p<0.001).

**Notion**: research_depth -0.58 (압도적). 꼼꼼한 PM일수록 결정 못 함. 분석 마비. 4개 플랜 비교가 인지부담.

**Linear**: impulsiveness +0.39. 즉시 호감으로 결정. 디자인 철학과 일치. 단, 결제 직전 마찰 60%.

**Figma**: privacy_sensitivity +0.24 (특이). 프라이버시 민감 사용자가 오히려 높은 outcome — Figma의 권한/팀 관리 명확함이 신뢰 신호로 작동.

세 사이트 모두 즉시 결제 = 0건/20명. 모두 "검토(partial)" 또는 "포기" — 가격 페이지의 실제 funnel 현실과 일치.

**Cross-cohort 메타** (9개 사이트 합산): 충동성·리서치 깊이·가격 민감도 = 9개 사이트 중 7개에서 일관된 방향. 사이트 종류와 무관 = 검증된 페르소나 핵심 차원 3가지.

오픈소스 + 재현 가능: github.com/kimtaeyoon83/41r-advisor

긴 분석: [SAAS_PRICING_COHORTS.md](https://github.com/kimtaeyoon83/41r-advisor/blob/main/41r/experiments/public_analysis/SAAS_PRICING_COHORTS.md)

---

⚠️ AI-generated synthetic research, not consumer reviews. 절대 수치 (전환율 등) 사용 금지 — 상대 비교만 유효.

#ProductManagement #UXResearch #LLMAgents #SaaS #ABTesting

---

## B. X (Twitter) 스레드 버전 (10 트윗)

**Tweet 1/10**
PM·디자이너·엔지니어 페르소나 60명(AI)이 Notion · Linear · Figma 가격 페이지를 검토했습니다.

n=200 ablation으로 검증된 모델 (+16%p over demographic baseline, p<0.001).

흥미로운 패턴 3가지 발견:

🧵

**Tweet 2/10**
1️⃣ Notion: research_depth -0.58 (압도적)

꼼꼼한 PM일수록 → 결정 못 함.

전형적인 분석 마비. 4개 플랜 × 다수 feature 비교표가 신중한 사용자를 압도.

→ 비교 인지부담 줄이는 게 KPI 될 듯

**Tweet 3/10**
2️⃣ Linear: impulsiveness +0.39

즉시 호감으로 결정. 깊이 비교 안 함.

Linear의 단순함·명확성 디자인 철학과 일치.

단, 위험 신호: partial(검토만) 60% — 결제 직전 마찰

**Tweet 4/10**
3️⃣ Figma: privacy_sensitivity +0.24 (양의 상관 — 특이)

대부분 SaaS에서는 프라이버시 민감 = 가입 부담.

Figma는 반대. 권한/팀 관리 구조가 명확해서 프라이버시 민감 사용자에게 신뢰 신호로 작동.

**Tweet 5/10**
세 사이트 모두 즉시 결제 = 0건/20명.

모두 "검토" 또는 "포기".

이게 실제 가격 페이지 funnel 현실 — AI가 결제 환상을 만들지 않는다는 신호.

**Tweet 6/10**
Cross-cohort 메타 (9개 사이트 합산):

검증된 페르소나 핵심 차원 3가지 (78% 사이트 일관):
- 충동성 → outcome ↑
- 리서치 깊이 → outcome ↓ (분석 마비)
- 가격 민감도 → outcome ↓

사이트 카테고리와 무관.

**Tweet 7/10**
사이트 의존적 trait 4가지:
- privacy_sensitivity
- visual_dependency
- tech_literacy
- social_proof_weight

이건 사이트 context와 함께 해석해야 함.

이걸 무시하면 페르소나 모델 잘못 사용.

**Tweet 8/10**
한계 (정직 고지):
- 시뮬레이션 (실제 사용자 0명)
- 절대 수치 GA4 대비 6~21× 과대평가 → 상대 비교만
- N=20/사이트 (작음)
- 한국 페르소나 풀 기반

**Tweet 9/10**
오픈소스 + 재현 가능:

github.com/kimtaeyoon83/41r-advisor

```
make verify-all
```

n=200 ablation, Bootstrap CI, Cross-cohort 메타, CATE validator, hallucination guard 모두 한 명령으로 재현.

**Tweet 10/10**
긴 분석:
github.com/kimtaeyoon83/41r-advisor/blob/main/41r/experiments/public_analysis/SAAS_PRICING_COHORTS.md

방법론 paper draft:
github.com/kimtaeyoon83/41r-advisor/blob/main/41r/bench/PAPER_DRAFT.md

피드백·이슈 환영 🙏

---

## C. Show HN 버전

**Title**: Show HN: 41R Persona Bench — reproducible LLM persona eval for pre-A/B segment divergence

**Body**:

Hi HN,

I've been working on a reproducible benchmark for LLM personas applied to pre-A/B-test design. Most LLM persona work targets *winner prediction* (which is unreliable, per recent papers). I reframed the question to *segment divergence detection* — predicting which user segments will react differently before any A/B test is run.

**Result on n=200 Upworthy A/B headlines**: persona profiles detect divergence at +16%p over demographic-only baseline (95% CI [+9.5, +22.5]%p, McNemar p=0.000009). Winner accuracy is statistically equivalent to baseline (-6%p, CI includes 0) — so I claim divergence detection, not winner prediction.

**Cross-site generalizability**: 9 commercial sites (e-commerce, SaaS, content). 3 traits (impulsiveness, research_depth, price_sensitivity) show 78% direction-consistency across sites — these are the validated "core dimensions". Other 4 traits are site-context-dependent.

**Reality check**: GA4 cross-validation shows 6~21× over-estimation on absolute numbers. Use for relative comparisons only.

**What's in the bench**:
- n=200 ablation + paired bootstrap CI
- Cross-cohort consistency analysis (9 sites)
- CATE Validator (EconML CausalForestDML; naive fallback)
- Hallucination guard with p-value recompute
- 49 unit tests

```
git clone https://github.com/kimtaeyoon83/41r-advisor
cd 41r-advisor/41r
make verify-all
```

Cost to reproduce: ~$0 from cached results, ~$30 for full ablation rerun.

Limitations honestly disclosed in `bench/PAPER_DRAFT.md` (Hu & Collier 2024, Lin "Six Fallacies" 2025 considered).

Looking for feedback on:
1. Is "segment divergence" a useful frame for pre-A/B design, or do you actually want winner prediction?
2. Are there public A/B datasets beyond Upworthy I should validate on?
3. Anyone interested in F2 NDA cross-validation with real customer A/B data?

Repo: https://github.com/kimtaeyoon83/41r-advisor

---

## 발행 전 체크리스트

- [ ] AI-generated synthetic research disclosure 포함 (모든 게시물)
- [ ] FTC Consumer Review Rule 회피 워딩 ("AI persona" 표현 OK; "review" 단어 회피)
- [ ] EU AI Act Article 50 라벨링 (외부 게시 시)
- [ ] GitHub repo public 상태 확인
- [ ] 대표 메일 응답 가능 상태 확인 (interest 들어올 경우)
- [ ] 한 곳만 발행 vs 동시 다발 (실험 설계: 채널별 lead 분리)
