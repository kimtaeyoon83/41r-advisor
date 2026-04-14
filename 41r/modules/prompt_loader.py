"""Prompt Loader — Hot Zone 프롬프트 로드 + references 자동 주입."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parent.parent
_PROMPTS_DIR = _BASE_DIR / "prompts"
_SHARED_DIR = _PROMPTS_DIR / "_shared"

# playbook reference → 공용 스니펫 파일 매핑
_REFERENCE_MAP = {
    "playbook/observation": "playbook_observation.md",
    "playbook/action_vocab": "playbook_action_vocab.md",
    "playbook/timing": "playbook_timing.md",
    "playbook/failure_modes": "playbook_failure_modes.md",
    "playbook/quality_gate": "playbook_quality_gate.md",
}


def load_prompt(prompt_path: str) -> str:
    """프롬프트 로드 + references 자동 주입.

    Args:
        prompt_path: prompts/ 이하 상대 경로 (예: 'agent/decision_judge')

    Returns:
        frontmatter 제거 후 references 주입된 최종 프롬프트 텍스트
    """
    dir_path = (_PROMPTS_DIR / prompt_path).resolve()
    if not dir_path.is_relative_to(_PROMPTS_DIR.resolve()):
        raise ValueError(f"Invalid prompt path: {prompt_path}")
    manifest_path = dir_path / "manifest.yaml"

    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest at {dir_path}")

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    current = manifest.get("current", "v001")
    prompt_file = dir_path / f"{current}.md"
    raw = prompt_file.read_text(encoding="utf-8")

    # frontmatter 파싱
    frontmatter, body = _split_frontmatter(raw)

    # references 주입
    references = frontmatter.get("references", [])
    injected_snippets = _load_references(references)

    if injected_snippets:
        body = body + "\n\n---\n\n# Reference Knowledge\n\n" + "\n\n".join(injected_snippets)

    return body.strip()


def load_prompt_with_meta(prompt_path: str) -> tuple[dict, str]:
    """프롬프트 + frontmatter 메타데이터 반환."""
    dir_path = (_PROMPTS_DIR / prompt_path).resolve()
    if not dir_path.is_relative_to(_PROMPTS_DIR.resolve()):
        raise ValueError(f"Invalid prompt path: {prompt_path}")
    manifest_path = dir_path / "manifest.yaml"

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    current = manifest.get("current", "v001")
    prompt_file = dir_path / f"{current}.md"
    raw = prompt_file.read_text(encoding="utf-8")

    frontmatter, body = _split_frontmatter(raw)
    references = frontmatter.get("references", [])
    injected_snippets = _load_references(references)

    if injected_snippets:
        body = body + "\n\n---\n\n# Reference Knowledge\n\n" + "\n\n".join(injected_snippets)

    meta = {
        **frontmatter,
        "version": current,
        "path": prompt_path,
    }

    return meta, body.strip()


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """YAML frontmatter 분리."""
    match = re.match(r"^---\n(.*?\n)---\n?(.*)", raw, re.DOTALL)
    if match:
        fm = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
        return fm, body
    return {}, raw


def _load_references(references: list[str]) -> list[str]:
    """reference 목록 → 스니펫 텍스트 목록."""
    snippets = []
    for ref in references:
        filename = _REFERENCE_MAP.get(ref)
        if filename:
            path = _SHARED_DIR / filename
            if path.exists():
                snippets.append(path.read_text(encoding="utf-8").strip())
    return snippets
