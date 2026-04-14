# 41R Persona Bench — Reproducible Evaluation Suite

> **Persona-based segment divergence detection** for pre-A/B-test design decisions.
> Validated on n=200 Upworthy headline A/B tests + 6 live SaaS/E-commerce sites.

## What this is

41R Persona Bench is a reproducible evaluation framework for **LLM-based persona simulations** that aim to predict **heterogeneous user reactions** before a real A/B test is run.

Unlike LLM persona work that targets *winner prediction* (which our results show is no better than demographic baseline), this bench measures **segment divergence detection** — whether persona-level simulations can identify *which* user segments will react differently to a proposed change.

**Key result**: Persona profiles ("Soul" v002 — 5 personality dimensions + frustration triggers + trust signals) detect segment divergence at **+16%p over demographic-only baseline (95% CI: +9.5~+22.5%p, McNemar p=0.000009)** on n=200 Upworthy A/B tests.

## Quick reproduction

```bash
cd 41r
make verify-all
```

Runs full pipeline:
1. n=200 ablation Bootstrap CI (`bootstrap-ci`)
2. CATE Validator self-demo (`cate-demo`)
3. Cross-cohort meta analysis (`cross-cohort`)
4. Executive report dynamic render (`render-exec`)
5. Claim auto-tagging (`tag-reports`)
6. Hallucination guard audit (`audit`)
7. 49 unit tests (`test`)

## Bench contents

| Component | Path | Purpose |
|---|---|---|
| **n=200 Ablation** | `experiments/ablation/results_ablation_n200.json` | Demo-only vs Demo+Soul on 200 Upworthy A/B headlines |
| **Bootstrap CI** | `experiments/ablation/bootstrap_ci_n200.json` | Paired bootstrap (n=1000) for divergence/accuracy CI |
| **Cross-Cohort Meta** | `experiments/cross_cohort_meta/meta.json` | Trait→outcome consistency across 6 live sites |
| **CATE Validator** | `modules/cate_validator.py` | EconML CausalForestDML / naive segment-diff |
| **CATE Self-Demo** | `experiments/cate_self_demo/result.json` | Methodology demo on synthetic A/B from ablation data |
| **Hallucination Guard** | `modules/hallucination_guard.py` | Auto-verify report claims (ground-truth + p-value recompute) |
| **Reality Check** | `modules/benchmark_loader.py` | GA4 + Open Bandit baseline for absolute-number sanity |

## Datasets

| Dataset | License | Path | Use |
|---|---|---|---|
| **Upworthy Research Archive** | CC BY 4.0 | `experiments/datasets/upworthy/` | Primary A/B validation (n=200 sample of 4,873 tests) |
| **GA4 Sample (BigQuery)** | Public | `experiments/datasets/ga4_sample/` | Absolute-number reality check |
| **Open Bandit (ZOZOTOWN)** | CC BY 4.0 | `experiments/datasets/open_bandit/` | CTR sanity check |

All Tier-1 (commercial-use OK). RetailRocket / Coveo / H&M Kaggle (CC BY-NC-SA) intentionally excluded.

## Personas (15-strong pool)

- **Manual basic 5**: `p_impulsive`, `p_cautious`, `p_budget`, `p_pragmatic`, `p_senior`
- **Manual extended 5**: `p_b2b_buyer`, `p_genz_mobile`, `p_parent_family`, `p_creator_freelancer`, `p_overseas_kor`
- **Demo baseline 5**: `demo_young_m`, `demo_adult_f`, `demo_adult_f2`, `demo_adult_m`, `demo_senior_f` (ablation control arm — nnage/gender/job only)

Soul v002 schema: 5 personality dimensions (impulsiveness, research_depth, price_sensitivity, visual_dependency, social_proof_weight) + generational traits + frustration triggers + trust signals.

Auto-generation via Latin Hypercube sampling: `modules/persona_generator.py`.

## Methodology summary

### Ablation (H1.1 — marginal value)

- **Arm A**: Demo-only personas (age/gender/region/job)
- **Arm B**: Demo + Soul (full 41R persona)
- Same LLM (Sonnet 4.6), same seed, same 200 cases (Upworthy, 50% swapped)
- Cache disabled (`core.cache.cache_disabled()`)
- Paired McNemar on case-by-case segment_divergence detection

### Cross-cohort consistency (persona generalizability)

For each of 6 live sites (Figma, 29CM, Class101, Ohouse, Webflow, Glossier):
- Generate 20 personas via Latin Hypercube
- Run text-mode simulation
- Compute trait → outcome Pearson correlation

Then aggregate across sites:
- `direction_agreement` per trait = fraction of sites with same sign
- `mean_corr` per trait
- Most consistent trait + biggest outlier site

### CATE validation (H2 entry point)

For F2 partner integration:
- Customer provides A/B data: `[{user_id, variant, outcome, segment}, ...]`
- 41R provides predicted diverging segments
- `cate_validator.validate_predictions()` runs EconML CausalForestDML (or naive segment-diff fallback)
- Output: F1 agreement, per-segment CATE with 95% CI, winner accuracy

## Honest limitations

1. **Absolute-number prediction is unreliable.** GA4 reality check shows 14~19× over-estimation for conversion rates, 2.4× for pageviews. Use for *relative comparison only*.
2. **A/B winner prediction is not our strength.** Bootstrap CI [-12, +0]%p includes 0 — Demo baseline is statistically equivalent.
3. **No customer cross-validation yet.** F2 NDA partner pipeline is the planned validation. Until then, all live-site cohort results are simulation-only.
4. **Persona pool is Korean-context-biased.** 15 personas reflect KR-Seoul demographics. International generalization untested.
5. **LLM persona homogenization** (Hu & Collier 2024, Lin "Six Fallacies" 2025) — accept structural limitations of the genre.

## Citations to consider

- Park et al., *Generative Agent Simulations of 1,000 People* (Stanford, arXiv 2411.10109, 2024) — fidelity baseline for the genre
- Chernozhukov et al., *Generic ML Inference on HTE in Randomized Experiments* (Econometrica, July 2025) — CATE methodology
- Rank-Preserving Calibration of LLMs (RAPCal, OpenReview 2025) — relative vs absolute claim theory
- Lin (2025), *Six Fallacies in Substituting LLMs for Human Participants* — pre-empted limitations
- Patterns, Not People — Alan Turing Institute CETaS (2025) — cohort-level only

## Status

| Component | Status |
|---|---|
| Ablation + Bootstrap CI | ✅ Validated |
| Cross-cohort consistency | ✅ Validated (6 sites) |
| CATE Validator workflow | ✅ Self-demo passing (F1=0.75) |
| Customer A/B cross-check | ⏳ F2 NDA pipeline pending |
| Hallucination guard coverage | ✅ Critical=0 across 4 reports |
| EconML installed in production | ⚠️ Lazy fallback; install for H2 |

## License

Code: MIT. Bench data: see individual dataset licenses (Upworthy CC BY 4.0, etc.).

## Citation

```bibtex
@misc{41r_persona_bench_2026,
  title={41R Persona Bench: Reproducible Evaluation of LLM Personas for Pre-A/B Segment Divergence Detection},
  author={Kim, Tae-yoon},
  year={2026},
  howpublished={\url{https://github.com/kimtaeyoon83/41r-advisor}},
}
```
