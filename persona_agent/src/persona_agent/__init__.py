"""persona_agent — Calibrated-persona analysis engine.

Public API is exposed here. Everything under ``persona_agent._internal`` is
private and may change without notice.

Typical embedding pattern::

    import persona_agent as pa
    pa.configure(pa.Workspace(root=..., ...))
    from persona_agent.lowlevel import run_cohort, generate_cohort_report
    result = run_cohort("cohort_xxx", url, task, mode="text")

The high-level async job API (``submit_analysis``, ``get_status``, ``get_result``)
is intentionally not shipped in 0.2.0 — wrap ``lowlevel`` calls in your own
queue (Celery/RQ/SQS). See CHANGELOG for the 0.3.0 plan.
"""

from persona_agent.errors import (
    ConfigurationError,
    CohortError,
    GuardrailError,
    HallucinationFoundError,
    LLMError,
    MissingExtraError,
    PersonaAgentError,
    PersonaError,
    PersonaExistsError,
    PersonaNotFoundError,
    PlanError,
    ProvenanceError,
    SessionError,
    UntaggedClaimError,
    BrowserError,
    VisionError,
)
from persona_agent.settings import Settings
from persona_agent.workspace import Workspace, configure, get_workspace

__version__ = "0.2.0.dev0"


def __getattr__(name: str):
    """Lazy access to ``lowlevel`` and ``list_personas``.

    Importing the facade itself must not trigger imports of internal modules
    (whose import-time path resolution would fail without a configured
    workspace). The embedding service should configure() before using
    lowlevel.
    """
    if name == "lowlevel":
        import importlib

        mod = importlib.import_module("persona_agent.lowlevel")
        globals()["lowlevel"] = mod
        return mod
    if name == "list_personas":
        from persona_agent.lowlevel import list_personas as _lp

        globals()["list_personas"] = _lp
        return _lp
    raise AttributeError(f"module 'persona_agent' has no attribute {name!r}")


__all__ = [
    "__version__",
    # Config
    "Settings",
    "Workspace",
    "configure",
    "get_workspace",
    # Queries
    "list_personas",
    # Power-user namespace
    "lowlevel",
    # Errors
    "PersonaAgentError",
    "ConfigurationError",
    "MissingExtraError",
    "SessionError",
    "BrowserError",
    "VisionError",
    "PlanError",
    "LLMError",
    "CohortError",
    "GuardrailError",
    "HallucinationFoundError",
    "UntaggedClaimError",
    "ProvenanceError",
    "PersonaError",
    "PersonaNotFoundError",
    "PersonaExistsError",
]
