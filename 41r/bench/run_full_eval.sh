#!/usr/bin/env bash
# 41R Persona Bench — Full evaluation reproduction.
#
# Runs the entire bench pipeline from clean state:
#   1. n=200 ablation Bootstrap CI
#   2. CATE Validator self-demo
#   3. Cross-cohort meta analysis
#   4. EXECUTIVE_REPORT dynamic render
#   5. Claim auto-tagging
#   6. Hallucination guard audit
#   7. 49 unit tests
#
# Cost: ~$0 (all uses pre-computed ablation data; no LLM calls).
# Time: ~20s on modern laptop.
#
# Usage:
#   cd 41r/
#   ./bench/run_full_eval.sh
#
# Or via Makefile:
#   make verify-all

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==========================================================="
echo "41R Persona Bench — Full Evaluation"
echo "==========================================================="
echo ""

# Sanity: required files exist
for f in \
  experiments/ablation/results_ablation_n200.json \
  experiments/datasets/ga4_sample/q1_funnel_drop.csv \
  experiments/datasets/open_bandit/sample_all.csv; do
  if [ ! -f "$f" ]; then
    echo "❌ Missing: $f"
    echo "   Run the data-fetching scripts first or check repo integrity."
    exit 1
  fi
done

echo "✓ All required data files present"
echo ""
echo "--- 1/7 Bootstrap CI on n=200 ablation ---"
.venv/bin/python3 experiments/ablation/bootstrap_ci.py

echo ""
echo "--- 2/7 CATE Validator self-demo ---"
.venv/bin/python3 experiments/cate_self_demo/run_self_demo.py

echo ""
echo "--- 3/7 Cross-cohort meta analysis ---"
.venv/bin/python3 -m modules.cross_cohort_meta

echo ""
echo "--- 4/7 EXECUTIVE_REPORT dynamic render ---"
.venv/bin/python3 scripts/render_executive.py

echo ""
echo "--- 5/7 Claim auto-tagging (high-confidence only) ---"
for f in reports/EXECUTIVE_REPORT.html reports/SIMPLE_REPORT.html reports/sample_report_v2.html; do
  if [ -f "$f" ]; then
    echo "  Tagging $f"
    .venv/bin/python3 -m modules.claim_tagger "$f" --apply 2>&1 | tail -2 || true
  fi
done

echo ""
echo "--- 6/7 Hallucination guard audit ---"
make audit

echo ""
echo "--- 7/7 Unit tests ---"
.venv/bin/python3 -m pytest tests/ -q

echo ""
echo "==========================================================="
echo "✓ Bench evaluation complete."
echo "  Key outputs:"
echo "    experiments/ablation/bootstrap_ci_n200.json"
echo "    experiments/cate_self_demo/SUMMARY.md"
echo "    experiments/cross_cohort_meta/REPORT.md"
echo "    reports/EXECUTIVE_REPORT.html (dynamic)"
echo "==========================================================="
