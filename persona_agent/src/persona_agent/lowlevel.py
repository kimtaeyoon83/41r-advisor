"""Power-user / synchronous API surface.

The high-level async job API is deliberately not shipped in 0.2.0 — the
embedding SaaS wraps these synchronous primitives in its own queue
(Celery/RQ/SQS). See `/home/kimtayoon/.claude/plans/sorted-giggling-puzzle.md`
for rationale.

These re-exports are stable across 0.x minor bumps. Signatures may evolve;
breaking changes will be documented in the changelog.
"""

# Session
from persona_agent._internal.session.agent_loop import (
    run_session,
)

# Cohort
from persona_agent._internal.cohort.cohort_runner import (
    run_cohort,
)
from persona_agent._internal.cohort.cohort_report import (
    aggregate_cohort,
    render_cohort_html,
    generate_cohort_report,
)

# Persona
from persona_agent._internal.persona.persona_store import (
    create_persona,
    read_persona,
    list_personas,
    append_observation,
    append_reflection,
    persona_at,
)
from persona_agent._internal.persona.persona_generator import (
    CohortSpec,
    generate_cohort,
)
from persona_agent._internal.persona.relations import (
    append_relation,
    list_relations,
    compute_similarity as compute_persona_similarity,
)
from persona_agent._internal.persona.schema_validator import (
    validate_soul,
    parse_soul_frontmatter,
)

# Integrity
from persona_agent._internal.integrity.hallucination_guard import (
    audit_report,
    audit_numbers,
    audit_pvalues,
    audit_tagged_claims,
    generate_audit_trail,
)
from persona_agent._internal.integrity.claim_tagger import (
    suggest_tags,
    apply_tags,
    coverage_report as claim_coverage_report,
)
from persona_agent._internal.integrity.provenance import (
    record as record_provenance,
    verify_chain,
)

# Analysis
from persona_agent._internal.analysis.cate_validator import (
    validate_predictions,
)
from persona_agent._internal.analysis.cross_cohort_meta import (
    run as run_meta,
    render_markdown as render_meta_markdown,
)
from persona_agent._internal.analysis.benchmark_loader import (
    get_baseline,
    diagnose_cohort,
)

# Reports
from persona_agent._internal.reports.report_gen import (
    generate_report,
)
from persona_agent._internal.reports.review_agent import (
    inspect as inspect_session,
    evaluate as evaluate_session,
)

__all__ = [
    # Session
    "run_session",
    # Cohort
    "run_cohort",
    "aggregate_cohort",
    "render_cohort_html",
    "generate_cohort_report",
    # Persona
    "create_persona",
    "read_persona",
    "list_personas",
    "append_observation",
    "append_reflection",
    "persona_at",
    "CohortSpec",
    "generate_cohort",
    # Relations + schema
    "append_relation",
    "list_relations",
    "compute_persona_similarity",
    "validate_soul",
    "parse_soul_frontmatter",
    # Integrity
    "audit_report",
    "audit_numbers",
    "audit_pvalues",
    "audit_tagged_claims",
    "generate_audit_trail",
    "suggest_tags",
    "apply_tags",
    "claim_coverage_report",
    "record_provenance",
    "verify_chain",
    # Analysis
    "validate_predictions",
    "run_meta",
    "render_meta_markdown",
    "get_baseline",
    "diagnose_cohort",
    # Reports
    "generate_report",
    "inspect_session",
    "evaluate_session",
]
