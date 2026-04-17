"""Public API — Persona CRUD, generation, relations, schema."""

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
    compute_similarity,
)
from persona_agent._internal.persona.schema_validator import (
    validate_soul,
    parse_soul_frontmatter,
)

__all__ = [
    "create_persona",
    "read_persona",
    "list_personas",
    "append_observation",
    "append_reflection",
    "persona_at",
    "CohortSpec",
    "generate_cohort",
    "append_relation",
    "list_relations",
    "compute_similarity",
    "validate_soul",
    "parse_soul_frontmatter",
]
