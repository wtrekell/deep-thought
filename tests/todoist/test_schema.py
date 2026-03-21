from pathlib import Path

import pytest

from deep_thought.todoist.db.schema import get_data_dir, get_database_path


class TestGetDataDir:
    def test_returns_default_path_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEP_THOUGHT_DATA_DIR", raising=False)
        result = get_data_dir()
        assert result.parts[-2:] == ("data", "todoist")

    def test_returns_env_override_when_set(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        result = get_data_dir()
        assert result == tmp_path

    def test_database_path_uses_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DEEP_THOUGHT_DATA_DIR", str(tmp_path))
        db_path = get_database_path()
        assert db_path == tmp_path / "todoist.db"
