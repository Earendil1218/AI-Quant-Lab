"""项目路径配置的离线测试。"""

from __future__ import annotations

from pathlib import Path

from config import settings


def test_project_paths_use_pathlib() -> None:
    assert isinstance(settings.PROJECT_ROOT, Path)
    assert isinstance(settings.DATA_DIR, Path)
    assert isinstance(settings.RAW_DATA_DIR, Path)
    assert isinstance(settings.PROCESSED_DATA_DIR, Path)


def test_project_root_is_derived_from_settings_location() -> None:
    expected_root = Path(settings.__file__).resolve().parents[1]

    assert settings.PROJECT_ROOT == expected_root


def test_data_directory_relationships() -> None:
    assert settings.DATA_DIR == settings.PROJECT_ROOT / "data"
    assert settings.RAW_DATA_DIR == settings.DATA_DIR / "raw"
    assert settings.PROCESSED_DATA_DIR == settings.DATA_DIR / "processed"
