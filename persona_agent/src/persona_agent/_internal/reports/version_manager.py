"""M7 Version Manager — append-only 파일 버전 관리 + manifest.

Versioned Document 패턴:
  {any_path}/
    v001.{ext}
    v002.{ext}
    manifest.yaml     # current 버전 지정 + 메타데이터

규칙:
- 모든 변경은 새 파일 생성 (append-only, 삭제 없음)
- 롤백 = manifest.current 필드 변경
- Review Agent의 proposal이 승인되면 Version Manager만이 prompts/에 쓰기 권한
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from persona_agent._internal.core.cache import content_hash
from persona_agent._internal.core.events_log import append as log_event
from persona_agent._internal.core.workspace import get_workspace

_BASE_DIR = get_workspace().root


def _read_manifest(dir_path: Path) -> dict:
    manifest_path = dir_path / "manifest.yaml"
    if not manifest_path.exists():
        return {"current": None, "versions": {}}
    with open(manifest_path) as f:
        return yaml.safe_load(f) or {"current": None, "versions": {}}


def _write_manifest(dir_path: Path, manifest: dict) -> None:
    with open(dir_path / "manifest.yaml", "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True)


def _next_version(manifest: dict) -> str:
    """manifest에서 다음 버전 번호 계산."""
    versions = manifest.get("versions", {})
    if not versions:
        return "v001"
    nums = []
    for v in versions:
        m = re.match(r"v(\d+)", v)
        if m:
            nums.append(int(m.group(1)))
    return f"v{max(nums) + 1:03d}" if nums else "v001"


def _detect_ext(dir_path: Path) -> str:
    """기존 파일에서 확장자 추론. 기본 .md"""
    for f in dir_path.glob("v*.*"):
        return f.suffix
    return ".md"


def save_version(path: str, content: str, author: str, message: str) -> str:
    """새 버전 저장. path는 prompts/ 이하 상대 경로 (예: 'agent/decision_judge').

    Returns: 생성된 버전 ID (예: 'v016')
    """
    dir_path = (_BASE_DIR / path).resolve()
    if not dir_path.is_relative_to(_BASE_DIR.resolve()):
        raise ValueError(f"Path traversal rejected: {path}")
    dir_path.mkdir(parents=True, exist_ok=True)

    manifest = _read_manifest(dir_path)
    version_id = _next_version(manifest)
    ext = _detect_ext(dir_path)

    # 새 파일 생성
    file_path = dir_path / f"{version_id}{ext}"
    file_path.write_text(content, encoding="utf-8")

    # manifest 업데이트
    if "versions" not in manifest:
        manifest["versions"] = {}
    manifest["versions"][version_id] = {
        "created": datetime.now(timezone.utc).isoformat(),
        "author": author,
        "message": message,
        "hash": content_hash(content),
    }
    manifest["current"] = version_id
    _write_manifest(dir_path, manifest)

    log_event({
        "type": "prompt_changed",
        "path": path,
        "from": _previous_version(manifest, version_id),
        "to": version_id,
        "author": author,
        "hash": content_hash(content),
    })

    return version_id


def get_current(path: str) -> str:
    """현재 활성 버전의 콘텐츠 반환."""
    dir_path = _BASE_DIR / path
    manifest = _read_manifest(dir_path)
    current = manifest.get("current")
    if not current:
        raise FileNotFoundError(f"No current version at {path}")

    ext = _detect_ext(dir_path)
    file_path = dir_path / f"{current}{ext}"
    return file_path.read_text(encoding="utf-8")


def get_version(path: str, version: str) -> str:
    """특정 버전의 콘텐츠 반환."""
    dir_path = _BASE_DIR / path
    ext = _detect_ext(dir_path)
    file_path = dir_path / f"{version}{ext}"
    if not file_path.exists():
        raise FileNotFoundError(f"Version {version} not found at {path}")
    return file_path.read_text(encoding="utf-8")


def rollback(path: str, to_version: str, reason: str) -> None:
    """manifest.current를 지정 버전으로 변경. 파일은 삭제하지 않음."""
    dir_path = _BASE_DIR / path
    manifest = _read_manifest(dir_path)

    if to_version not in manifest.get("versions", {}):
        raise ValueError(f"Version {to_version} not found in manifest at {path}")

    prev_version = manifest.get("current")
    manifest["current"] = to_version
    _write_manifest(dir_path, manifest)

    log_event({
        "type": "rollback",
        "path": path,
        "from": prev_version,
        "to": to_version,
        "reason": reason,
    })


def get_lineage(report_id: str) -> dict:
    """리포트에 사용된 모든 프롬프트 버전 정보 수집 (agent + report Hot Zone).

    manifest에 hash가 없으면 현재 버전 파일 콘텐츠에서 런타임 계산.
    """
    lineage: dict = {}

    # Hot Zone 모든 영역 스캔: agent/, report/, review/
    scan_roots = [
        _BASE_DIR / "prompts" / "agent",
        _BASE_DIR / "prompts" / "report",
    ]

    for root in scan_roots:
        if not root.exists():
            continue
        for prompt_dir in sorted(root.iterdir()):
            if not prompt_dir.is_dir() or prompt_dir.name.startswith("_"):
                continue
            manifest = _read_manifest(prompt_dir)
            current = manifest.get("current")
            if not current:
                continue

            version_meta = manifest.get("versions", {}).get(current, {})
            file_hash = version_meta.get("hash", "")
            if not file_hash:
                # 런타임 hash 계산 (수동 작성 manifest 대응)
                ext = _detect_ext(prompt_dir)
                file_path = prompt_dir / f"{current}{ext}"
                if file_path.exists():
                    file_hash = content_hash(file_path.read_text(encoding="utf-8"))

            # namespace로 충돌 방지: root 이름을 prefix로
            key = f"{root.name}/{prompt_dir.name}"
            lineage[key] = {
                "version": current,
                "hash": file_hash,
                "path": str(prompt_dir.relative_to(_BASE_DIR)),
            }

    return lineage


def get_current_version_info(path: str) -> dict:
    """현재 활성 버전의 메타 정보 반환 (events log 용).

    Returns: {"version": "v002", "hash": "abc123...", "path": "prompts/agent/xxx"}
    """
    dir_path = _BASE_DIR / path
    if not dir_path.exists():
        return {"version": None, "hash": "", "path": path}

    manifest = _read_manifest(dir_path)
    current = manifest.get("current")
    if not current:
        return {"version": None, "hash": "", "path": path}

    version_meta = manifest.get("versions", {}).get(current, {})
    file_hash = version_meta.get("hash", "")
    if not file_hash:
        ext = _detect_ext(dir_path)
        file_path = dir_path / f"{current}{ext}"
        if file_path.exists():
            file_hash = content_hash(file_path.read_text(encoding="utf-8"))

    return {"version": current, "hash": file_hash, "path": path}


def _previous_version(manifest: dict, current: str) -> str | None:
    """현재 버전의 바로 이전 버전 찾기."""
    versions = sorted(manifest.get("versions", {}).keys())
    idx = versions.index(current) if current in versions else -1
    if idx > 0:
        return versions[idx - 1]
    return None
