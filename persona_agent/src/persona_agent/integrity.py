"""Public API — Integrity: hallucination guard, claim tagging, provenance."""

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
    coverage_report,
)
from persona_agent._internal.integrity.provenance import (
    record,
    verify_chain,
)

__all__ = [
    "audit_report",
    "audit_numbers",
    "audit_pvalues",
    "audit_tagged_claims",
    "generate_audit_trail",
    "suggest_tags",
    "apply_tags",
    "coverage_report",
    "record",
    "verify_chain",
]
