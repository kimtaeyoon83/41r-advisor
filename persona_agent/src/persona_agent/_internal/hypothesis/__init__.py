"""Hypothesis Planner (experimental, PR-14).

High-level API for business hypotheses. Translates a one-line product
question into executable per-persona tasks, runs them, and aggregates the
results into a verdict with supporting evidence.

Low-level paths (``run_session``, ``run_cohort``) remain available for
callers who want direct control.
"""
from persona_agent._internal.hypothesis.orchestrator import (
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
