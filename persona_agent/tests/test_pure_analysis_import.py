"""Verify that a pure-analysis caller can import persona_agent without
triggering any optional-extra imports (playwright, weasyprint, scipy, pandas).

This is the contract for the ``[analysis]`` extras subset: the top-level
facade and basic queries must work even when heavy deps are absent.
"""
from __future__ import annotations

import importlib
import sys


def test_top_level_import_does_not_pull_optional_extras():
    """Importing persona_agent must not eagerly load any heavy optional deps."""
    for mod in ("playwright", "weasyprint", "scipy", "pandas"):
        sys.modules.pop(mod, None)

    importlib.import_module("persona_agent")

    for mod in ("playwright", "weasyprint", "scipy", "pandas"):
        assert mod not in sys.modules, (
            f"{mod} was imported during `import persona_agent` — it must be "
            f"a lazy import inside the function that needs it."
        )


def test_lowlevel_namespace_import_is_safe():
    """``persona_agent.lowlevel`` itself must import without optional deps."""
    for mod in ("playwright", "weasyprint", "scipy", "pandas"):
        sys.modules.pop(mod, None)

    importlib.import_module("persona_agent.lowlevel")

    for mod in ("playwright", "weasyprint", "scipy", "pandas"):
        assert mod not in sys.modules, (
            f"{mod} was imported by `persona_agent.lowlevel` import — guard it"
        )
