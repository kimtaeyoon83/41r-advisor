# persona_agent

Calibrated-persona analysis engine. Reusable Python package extracted from the
41R research repo for embedding in external services.

## Status

**0.2.0.dev0 — PR-1 scaffold.** Public API is stubbed; the real engine is
wired in through PR-4. Current package exposes only:

- `persona_agent.Settings`, `Workspace`, `configure()`, `get_workspace()`
- Full exception hierarchy (`PersonaAgentError` and descendants)
- `__version__`

The analysis functions (`run_session`, `run_cohort`, `audit_report`, etc.)
land on `persona_agent.lowlevel` in PR-4.

## Layout

```
src/persona_agent/
├── __init__.py       # facade — public API only
├── lowlevel.py       # power-user re-exports (PR-4)
├── settings.py       # Settings dataclass
├── workspace.py      # Workspace + get_workspace/configure
├── errors.py         # exception hierarchy
├── _internal/        # private — may change without notice (PR-3/4)
└── data/             # bundled prompts, config, built-in personas (PR-3)
```

## Install (dev)

```bash
pip install -e "./persona_agent[dev]"
cd persona_agent && pytest
```

See `/home/kimtayoon/.claude/plans/sorted-giggling-puzzle.md` for the full
migration plan.
