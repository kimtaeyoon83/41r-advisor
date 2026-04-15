"""Deprecated location. Import from persona_agent._internal.core.events_log instead.

Kept during the PR-3→PR-7 migration window. Will be deleted once the
external service has cut over to persona_agent.
"""
import warnings

warnings.warn(
    f"{__name__} is a compatibility shim; import from persona_agent._internal.core.events_log instead.",
    DeprecationWarning,
    stacklevel=2,
)

from persona_agent._internal.core.events_log import *  # noqa: F401,F403,E402
from persona_agent._internal.core.events_log import __dict__ as _src_dict  # noqa: E402

# Expose private names too (tests monkeypatch _BASE_DIR, _PERSONAS_DIR, etc.)
globals().update({k: v for k, v in _src_dict.items() if not k.startswith("__")})
