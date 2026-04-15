"""Deprecated location. Import from persona_agent._internal.cohort.cohort_runner instead."""
import warnings

warnings.warn(
    f"{__name__} is a compatibility shim; import from persona_agent._internal.cohort.cohort_runner instead.",
    DeprecationWarning,
    stacklevel=2,
)

from persona_agent._internal.cohort.cohort_runner import *  # noqa: F401,F403,E402
from persona_agent._internal.cohort.cohort_runner import __dict__ as _src_dict  # noqa: E402

globals().update({k: v for k, v in _src_dict.items() if not k.startswith("__")})
