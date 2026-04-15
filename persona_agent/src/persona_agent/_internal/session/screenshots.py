"""Screenshot path inspection — pure-function helpers.

persona_agent only writes screenshots to the workspace filesystem. Uploading
them (S3, R2, CDN, etc) is the embedding server's concern. These helpers let
consumers enumerate what's on disk for a given session.
"""
from __future__ import annotations

from pathlib import Path

from persona_agent._internal.core.workspace import get_workspace


def list_session_screenshots(session_id: str) -> list[Path]:
    """Absolute paths of screenshots saved for ``session_id``, sorted by turn.

    Returns [] if the session never produced screenshots (e.g. text mode,
    browser disabled via ``save_screenshots=False``, or session doesn't exist
    yet).
    """
    if not session_id:
        return []
    ws = get_workspace()
    shots_dir = ws.session_screenshots_dir(session_id)
    if not shots_dir.exists():
        return []
    return sorted(shots_dir.glob("turn_*.png"))


def session_screenshots_dir(session_id: str) -> Path:
    """Expected path for this session's screenshots dir (may not exist yet).
    Thin wrapper around ``Workspace.session_screenshots_dir`` for import
    convenience from ``persona_agent.lowlevel``."""
    return get_workspace().session_screenshots_dir(session_id)
