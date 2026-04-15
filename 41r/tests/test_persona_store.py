"""M1 Persona Store 핵심 함수 단위 테스트."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from persona_agent._internal.persona import persona_store


@pytest.fixture
def tmp_personas_dir(monkeypatch, tmp_path):
    """임시 personas/ 디렉토리로 모듈 격리.

    PR-8 이후: workspace.builtin_personas_dir도 tmp로 빼야 실 레포
    `41r/personas/`가 overlay read에 끼어들지 않는다.
    """
    from persona_agent import Workspace, configure, get_workspace
    pdir = tmp_path / "personas"
    pdir.mkdir()
    prev = get_workspace()
    ws = Workspace(
        root=tmp_path,
        personas_dir=pdir,
        builtin_personas_dir=pdir,  # 테스트에선 builtin도 tmp로 고정
        prompts_dir=tmp_path / "prompts",
        config_dir=tmp_path / "config",
        reports_dir=tmp_path / "reports",
    )
    configure(ws)
    monkeypatch.setattr(persona_store, "_PERSONAS_DIR", pdir)
    yield pdir
    configure(prev)


def test_create_persona_creates_dirs(tmp_personas_dir):
    persona_store.create_persona("p_test", "test soul content")
    assert (tmp_personas_dir / "p_test" / "soul").exists()
    assert (tmp_personas_dir / "p_test" / "history").exists()
    assert (tmp_personas_dir / "p_test" / "reflections").exists()
    soul_file = tmp_personas_dir / "p_test" / "soul" / "v001.md"
    assert soul_file.exists()
    assert "test soul content" in soul_file.read_text(encoding="utf-8")


def test_read_persona_returns_state(tmp_personas_dir):
    persona_store.create_persona("p_test", "soul content")
    state = persona_store.read_persona("p_test")
    assert state.persona_id == "p_test"
    assert state.soul_version == "v001"
    assert "soul content" in state.soul_text
    assert state.observations == []
    assert state.reflections == []


def test_read_nonexistent_persona_raises(tmp_personas_dir):
    with pytest.raises((FileNotFoundError, ValueError)):
        persona_store.read_persona("p_does_not_exist")


def test_append_observation_with_required_fields(tmp_personas_dir):
    persona_store.create_persona("p_test", "soul")
    obs_id = persona_store.append_observation("p_test", {
        "persona_id": "p_test",
        "persona_version": "v001",
        "content": "saw a banner",
    })
    assert obs_id.startswith("o_")
    state = persona_store.read_persona("p_test")
    assert len(state.observations) == 1
    assert state.observations[0]["content"] == "saw a banner"


def test_append_observation_missing_required_field_raises(tmp_personas_dir):
    persona_store.create_persona("p_test", "soul")
    with pytest.raises((KeyError, ValueError)):
        persona_store.append_observation("p_test", {
            "content": "missing persona_id and version",
        })


def test_path_traversal_rejected(tmp_personas_dir):
    """persona_id에 '../' 같은 경로 traversal이 차단되는지."""
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        persona_store.read_persona("../../../etc/passwd")


def test_append_observation_immutable(tmp_personas_dir):
    """append-only 보장: 한 번 쓴 observation 파일은 수정 불가."""
    persona_store.create_persona("p_test", "soul")
    obs = {"persona_id": "p_test", "persona_version": "v001", "content": "test obs"}
    obs_id = persona_store.append_observation("p_test", obs)

    # 파일 콘텐츠 캡처
    obs_file = tmp_personas_dir / "p_test" / "history" / f"{obs_id}.json"
    original_content = obs_file.read_text(encoding="utf-8")

    # 같은 obs를 다시 append (timestamp 차이로 새 obs_id 생성됨 — 이게 정상)
    obs_id2 = persona_store.append_observation("p_test", obs)

    # 두 obs는 별개 파일 (timestamp 차이)
    assert obs_id != obs_id2 or obs_file.read_text(encoding="utf-8") == original_content
    # 원본 파일은 수정 안 됨 (immutable)
    assert obs_file.read_text(encoding="utf-8") == original_content
