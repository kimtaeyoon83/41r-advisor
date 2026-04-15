"""M7 Version Manager 핵심 함수 테스트."""
import pytest
from pathlib import Path

from persona_agent._internal.reports import version_manager


@pytest.fixture
def tmp_base(monkeypatch, tmp_path):
    """임시 base dir (prompts/ 등이 들어갈 곳)."""
    monkeypatch.setattr(version_manager, "_BASE_DIR", tmp_path)
    return tmp_path


def test_save_first_version(tmp_base):
    vid = version_manager.save_version(
        "prompts/agent/test_prompt",
        "first content",
        author="freddie",
        message="initial",
    )
    assert vid == "v001"
    assert (tmp_base / "prompts" / "agent" / "test_prompt" / "v001.md").exists()
    assert (tmp_base / "prompts" / "agent" / "test_prompt" / "manifest.yaml").exists()


def test_save_second_version_increments(tmp_base):
    version_manager.save_version("prompts/agent/test", "v1", "freddie", "init")
    vid = version_manager.save_version("prompts/agent/test", "v2", "freddie", "update")
    assert vid == "v002"


def test_get_current_returns_latest(tmp_base):
    version_manager.save_version("prompts/agent/test", "v1 content", "f", "init")
    version_manager.save_version("prompts/agent/test", "v2 content", "f", "update")
    current = version_manager.get_current("prompts/agent/test")
    assert "v2 content" in current


def test_get_version_specific(tmp_base):
    version_manager.save_version("prompts/agent/test", "v1", "f", "init")
    version_manager.save_version("prompts/agent/test", "v2", "f", "update")
    assert "v1" in version_manager.get_version("prompts/agent/test", "v001")
    assert "v2" in version_manager.get_version("prompts/agent/test", "v002")


def test_rollback_changes_current(tmp_base):
    version_manager.save_version("prompts/agent/test", "v1", "f", "init")
    version_manager.save_version("prompts/agent/test", "v2", "f", "update")
    version_manager.rollback("prompts/agent/test", "v001", "regression")
    assert "v1" in version_manager.get_current("prompts/agent/test")


def test_path_traversal_rejected(tmp_base):
    with pytest.raises(ValueError):
        version_manager.save_version("../../../etc/passwd", "x", "f", "evil")


def test_get_lineage_includes_hash(tmp_base):
    version_manager.save_version("prompts/agent/test", "content", "f", "init")
    lineage = version_manager.get_lineage("test_report")
    # tmp_base에는 agent/test 하나만 있으므로 키가 있어야 함
    keys = list(lineage.keys())
    # Hot Zone 스캔이 prompts/agent/, prompts/report/ 둘 다 보므로
    # 적어도 우리 prompt가 어딘가에는 있어야 함
    assert any("test" in k for k in keys), f"Expected 'test' in lineage keys: {keys}"
    for k, v in lineage.items():
        if "test" in k:
            assert v.get("hash"), f"Hash should be present in {v}"


def test_get_current_version_info(tmp_base):
    version_manager.save_version("prompts/agent/test", "content", "f", "init")
    info = version_manager.get_current_version_info("prompts/agent/test")
    assert info["version"] == "v001"
    assert info["hash"]  # not empty
    assert info["path"] == "prompts/agent/test"
