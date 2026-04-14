# Persona Profiles Detect Segment Divergence in Pre-A/B-Test Design: A Reproducible Evaluation

**Status**: Draft v0.1 — pre-arXiv

---

## Abstract

LLM-based persona simulations have been proposed for synthetic user research, but recent work (Hu & Collier 2024; Lin 2025) shows that *winner prediction* — asking which design variant will win an A/B test — is unreliable. We reframe the question: can persona profiles instead detect *segment divergence* — the prediction that different user segments will react differently to a proposed change, before any A/B test is run?

We evaluate this on **n=200 Upworthy A/B headline tests** with a paired ablation: identical LLM (Sonnet 4.6), identical seed, identical cases — varying only persona richness. The "Demo-only" arm uses age/gender/occupation labels; the "41R" arm adds a structured personality profile (5 dimensions: impulsiveness, research depth, price sensitivity, visual dependency, social proof weight) plus frustration triggers and trust signals.

**Result**: 41R detects segment divergence on **+16%p more cases than Demo-only** (95% CI: +9.5~+22.5%p, McNemar p=0.000009, paired bootstrap n=1000). Critically, A/B *winner prediction accuracy* shows **no significant improvement** (-6%p, 95% CI [-12, +0]%p, p=0.073) — confirming that personas add value for *divergence detection*, not winner prediction.

We further validate persona generalizability across 6 live commercial sites (e-commerce, SaaS, content): **price_sensitivity** and **research_depth** show direction-consistent influence on outcomes in 5/6 sites (direction agreement ≥ 0.83), while privacy and visual-dependency traits are site-dependent.

We release the bench, code, and data under MIT/CC-BY 4.0.

---

## 1. Introduction

The promise of LLM personas is that they can predict user reactions before real-world A/B testing. The reality, per recent work, is more constrained:

- **Hu & Collier (2024)**: persona effects are "shallow" — fine-grained individual prediction is unreliable.
- **Lin (2025)**: six fallacies in substituting LLMs for human participants; aggregation matters.
- **Patterns, Not People (CETaS 2025)**: LLM personas produce *patterns*, not individuals.

These findings suggest a pivot: instead of asking *who wins*, ask *whether segments will diverge*. This is a smaller, more defensible claim — and one that maps directly to a CPO's pre-A/B design decision: "should this change be tested as a single variant, or as a per-segment design?"

We validate this pivot on n=200 cases of real published A/B test results.

## 2. Method

### 2.1 Ablation design

| Element | Arm A (Demo-only) | Arm B (41R) |
|---|---|---|
| Persona count | 5 | 5 |
| Persona content | age, gender, region, occupation | + 5 personality dimensions + frustration triggers + trust signals |
| LLM | Sonnet 4.6 | Sonnet 4.6 (identical) |
| Seed | 42 | 42 |
| Cache | disabled | disabled |
| Cases | 200 (Upworthy, 50% swapped to control for label bias) | identical |

For each case, each persona produces a `predicted_winner ∈ {A, B}`. **Segment divergence** = 1 if any two personas in the arm predict different winners; **accuracy** = 1 if the arm's majority vote matches the actual winner.

### 2.2 Statistical tests

- **Primary**: Paired McNemar test on per-case `segment_divergence` — does Arm B detect divergence on more cases than Arm A given the same cases?
- **Secondary**: Paired McNemar on per-case `accuracy_match`.
- **Confidence intervals**: Paired bootstrap (n=1000) on case-level deltas, percentile method.

### 2.3 Cross-site generalizability

For 6 live commercial sites (Figma, 29CM, Class101, Ohouse, Webflow, Glossier):
1. Generate 20 personas via Latin Hypercube sampling (`modules/persona_generator`)
2. Run text-mode simulation of a representative purchase task
3. Compute Pearson correlation between each trait and outcome score (1.0=task_complete, 0.5=partial, 0.0=abandoned)
4. Aggregate: per-trait `direction_agreement` (fraction of sites with same correlation sign) and `mean_corr`

### 2.4 Reality check (absolute-number sanity)

Compare aggregate sim outcomes against GA4 Sample (Google Merchandise Store, public BigQuery) and Open Bandit (ZOZOTOWN, CC BY 4.0). Computed at report-render time via `modules/benchmark_loader`.

### 2.5 CATE validation pathway (planned)

For future H2-phase validation with NDA-partnered customers:
- Customer provides A/B data: `[{user_id, variant, outcome, segment}, ...]`
- Run EconML CausalForestDML (or naive segment-difference fallback) per `modules/cate_validator`
- Compute F1 agreement between 41R-predicted diverging segments and empirical CATE-revealed diverging segments

A self-demo using the n=200 ablation (treating demographic labels as segment IDs and Arm A/B as a synthetic treatment) achieves F1=0.75 on the segment recovery task, validating the workflow ahead of customer integration.

## 3. Results

### 3.1 Primary result: divergence detection

| Metric | Arm A (Demo) | Arm B (41R) | Δ | 95% CI (bootstrap n=1000) | p (McNemar) |
|---|---|---|---|---|---|
| **Segment divergence rate** | 42.5% | 58.5% | **+16.0%p** | **[+9.5, +22.5]%p** | **0.000009** |
| Winner accuracy | 61.0% | 55.0% | -6.0%p | [-12.0, 0.0]%p | 0.073 |

The divergence-detection improvement is statistically significant (CI excludes 0). The winner-accuracy difference is not (CI includes 0).

**Interpretation**: 41R personas do not predict A/B winners better than demographic labels alone. They do, however, identify **which cases will produce segment-divergent reactions** — a different and more defensible claim.

### 3.2 Cross-site trait consistency (n=6 sites, n=20 personas each)

| Trait | mean_corr | direction_agreement | Sites +/-/~ | Interpretation |
|---|---|---|---|---|
| **price_sensitivity** | -0.289 | **0.83** | 1/5/0 | Strong consistency — negative across sites |
| **research_depth** | -0.203 | **0.83** | 0/5/1 | Strong consistency — negative across sites |
| impulsiveness | +0.197 | 0.67 | 4/2/0 | Moderate |
| tech_literacy | -0.132 | 0.67 | 1/4/1 | Moderate |
| privacy_sensitivity | +0.117 | 0.50 | 3/2/1 | ⚠ Site-dependent |
| social_proof_weight | -0.070 | 0.50 | 1/3/2 | ⚠ Site-dependent |
| visual_dependency | -0.051 | 0.50 | 2/3/1 | ⚠ Site-dependent |

**Interpretation**: Two traits (price_sensitivity, research_depth) show direction-consistent influence on outcomes in 5/6 sites — these are candidate "core dimensions" of the persona model. The remaining traits' influence is site-context-dependent and should not be claimed as universal.

The biggest cross-site outlier is `glossier.com` (avg trait-correlation distance = 0.300 from mean of other sites), suggesting that international beauty e-commerce activates persona behaviors distinct from the other Korean-context sites tested.

### 3.3 Reality check (absolute-number disclaimer)

| Metric | 41R sim | GA4 (Google Merch) | Gap |
|---|---|---|---|
| Add-to-cart rate | ~30% | 4.7% | 6.4× over |
| Avg pageviews/session | 9.06 | 3.74 | 2.4× over |
| Mobile conversion rate | ~30% | 1.4% | 21× over |

**Conclusion**: 41R outputs **must not be used as absolute-number predictors**. They are validated for *relative* comparisons (segment divergence, A vs B preference) only.

## 4. Related work

- **UXAgent** (Lu et al., CHI EA 2025) — closest academic analogue; LLM agents browse real sites with a Universal Browser Connector. Differs in evaluation focus (agent capability vs statistical claim about persona value).
- **Generative Agents 1,000 People** (Park et al., Stanford, 2024) — 2-hour interview personas replicate GSS responses at 85% of human test-retest reliability. Establishes the genre's fidelity ceiling.
- **Customer-R1** (arXiv 2510.07230) — RL-trained step-wise shopping simulation. Outperforms prompted personas on task completion; orthogonal to the divergence-detection claim.
- **Generic ML Inference on HTE** (Chernozhukov et al., Econometrica 2025) — canonical method for the CATE validator pathway.
- **HEXACO with Generative Agents** (arXiv 2508.00742) — personality structure recoverable but variance-flattened. Motivates our Latin Hypercube sampling.

Commercial: **Aaru** ($1B Series A, Dec 2025) is the most prominent funded competitor, but operates on synthetic *polling*, not behavioral simulation on live products. **Maze, UserTesting, Lyssna, Dovetail** added AI summarization in 2024-25 but no equivalent persona-runs-product capability has shipped.

## 5. Limitations

1. **Single primary dataset (Upworthy headlines)**. Generalization to e-commerce CTAs, SaaS pricing pages, or mobile UX patterns requires per-domain validation.
2. **No customer ground-truth cross-check**. Live-site cohort results (§3.2) are simulation-only; they validate cross-site trait consistency *within* the simulator, not against real GA/Hotjar.
3. **Korean-context persona pool**. International generalizability untested.
4. **Text-mode simulation for cross-site analysis**. Browser-mode results (Phase B; available for 5 of 6 sites) show similar patterns but were not the primary input here.
5. **LLM persona homogenization** (Hu & Collier 2024). Mitigated structurally via Latin Hypercube sampling and per-trait variance injection, but residual flattening cannot be ruled out.
6. **Absolute-number predictions are 6-21× over-estimates** vs GA4 baseline. We do not claim absolute-number validity.

## 6. Reproducibility

```bash
git clone https://github.com/kimtaeyoon83/41r-advisor
cd 41r-advisor/41r
.venv/bin/python3 -m pip install -e .  # or use existing .venv
make verify-all
```

`make verify-all` runs:
1. `bootstrap-ci` — recomputes paired bootstrap CIs from `results_ablation_n200.json`
2. `cate-demo` — runs CATE validator self-demo
3. `cross-cohort` — recomputes cross-site consistency
4. `render-exec` — regenerates EXECUTIVE_REPORT with live numbers
5. `tag-reports` — auto-tags reports with ground-truth source spans
6. `audit` — hallucination guard verifies all numeric claims against ground truth (including p-value recompute via scipy)
7. `test` — 49 unit tests

All scripts under MIT license. Datasets under their original licenses (Upworthy CC BY 4.0; Open Bandit CC BY 4.0; GA4 sample is public).

## 7. Conclusion

LLM personas can be evaluated rigorously by reframing the question from *winner prediction* (where they fail) to *segment divergence detection* (where they succeed). The 41R persona profile achieves +16%p divergence detection over demographic-only baseline (CI [+9.5, +22.5]%p, n=200), and two of five trait dimensions show cross-site direction consistency. Absolute-number predictions remain unreliable; commercial use should be restricted to relative comparisons. We release the bench for community use.

---

**Author**: Kim Tae-yoon · **Date**: April 2026 · **Repo**: https://github.com/kimtaeyoon83/41r-advisor
