"""Public API — Hypothesis planning and execution."""

from persona_agent._internal.hypothesis import (
    plan_and_run_hypothesis,
    plan_hypothesis,
    rewrite_task_for_persona,
    aggregate_verdict,
    HypothesisPlan,
    HypothesisVerdict,
)

__all__ = [
    "plan_and_run_hypothesis",
    "plan_hypothesis",
    "rewrite_task_for_persona",
    "aggregate_verdict",
    "HypothesisPlan",
    "HypothesisVerdict",
]
