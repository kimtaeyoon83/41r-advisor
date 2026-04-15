"""Exception hierarchy for persona_agent.

Catch ``PersonaAgentError`` to handle any library failure. More specific
subclasses exist for targeted handling by the embedding service.
"""


class PersonaAgentError(Exception):
    """Root of all persona_agent errors."""


class ConfigurationError(PersonaAgentError):
    """Settings, workspace, or environment is misconfigured.

    Raised at ``configure()`` / ``load_settings()`` time, before any work runs.
    """


class MissingExtraError(PersonaAgentError):
    """A feature was used that requires an optional dependency not installed."""

    def __init__(self, extra: str, install_hint: str) -> None:
        super().__init__(
            f"Feature requires optional extra '{extra}'. Install with: {install_hint}"
        )
        self.extra = extra
        self.install_hint = install_hint


class SessionError(PersonaAgentError):
    """A single persona × URL × task session failed."""


class BrowserError(SessionError):
    """Playwright-level failure (navigation, timeout, closed page)."""


class VisionError(SessionError):
    """Vision-mode element location failed after all fallbacks."""


class PlanError(SessionError):
    """Agent loop could not produce a valid plan after N retries."""


class LLMError(SessionError):
    """Provider returned an error, malformed JSON, or the session exceeded budget."""


class CohortError(PersonaAgentError):
    """Cohort execution or aggregation failed.

    ``partial_result`` may be set when some sessions succeeded before the
    failure occurred.
    """

    def __init__(self, message: str, partial_result: dict | None = None) -> None:
        super().__init__(message)
        self.partial_result = partial_result


class GuardrailError(PersonaAgentError):
    """Integrity check (hallucination guard, claim tagger) blocked the output."""


class HallucinationFoundError(GuardrailError):
    """audit_report found a numeric, p-value, or claim inconsistent with ground truth."""


class UntaggedClaimError(GuardrailError):
    """Report contains claims without the required provenance tags."""


class ProvenanceError(PersonaAgentError):
    """provenance.verify_chain failed: HMAC mismatch or tamper detected.

    ``broken_at_index`` points to the first corrupt entry when known.
    """

    def __init__(self, message: str, broken_at_index: int | None = None) -> None:
        super().__init__(message)
        self.broken_at_index = broken_at_index


class PersonaError(PersonaAgentError):
    """Persona creation, read, or generation failed."""


class PersonaNotFoundError(PersonaError):
    """Requested persona id does not exist in the workspace or built-ins."""


class PersonaExistsError(PersonaError):
    """Cannot create persona: id already exists (including built-in collisions)."""
