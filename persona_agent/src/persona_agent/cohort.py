"""Public API — Cohort execution and reporting."""

from persona_agent._internal.cohort.cohort_runner import run_cohort
from persona_agent._internal.cohort.cohort_report import (
    aggregate_cohort,
    render_cohort_html,
    generate_cohort_report,
)

__all__ = [
    "run_cohort",
    "aggregate_cohort",
    "render_cohort_html",
    "generate_cohort_report",
]
