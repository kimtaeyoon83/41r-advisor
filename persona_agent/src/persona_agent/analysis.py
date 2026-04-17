"""Public API — Analysis utilities (CATE, cross-cohort meta, benchmarks, predicates)."""

from persona_agent._internal.analysis.cate_validator import validate_predictions
from persona_agent._internal.analysis.cross_cohort_meta import (
    run as run_meta,
    render_markdown as render_meta_markdown,
)
from persona_agent._internal.analysis.benchmark_loader import (
    get_baseline,
    diagnose_cohort,
)
from persona_agent._internal.analysis.predicate_scorer import (
    score_session_predicates,
    PredicateResult,
    ScoreResult,
)

__all__ = [
    "validate_predictions",
    "run_meta",
    "render_meta_markdown",
    "get_baseline",
    "diagnose_cohort",
    "score_session_predicates",
    "PredicateResult",
    "ScoreResult",
]
