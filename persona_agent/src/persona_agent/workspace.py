"""Public re-export of the workspace contract.

Canonical implementation lives at
``persona_agent._internal.core.workspace`` so internal modules can depend on
it without pulling in the top-level facade. External consumers should import
from ``persona_agent.workspace`` (or directly from ``persona_agent``).
"""
from persona_agent._internal.core.workspace import (
    Workspace,
    configure,
    get_workspace,
    _reset_for_tests,
)

__all__ = ["Workspace", "configure", "get_workspace"]
