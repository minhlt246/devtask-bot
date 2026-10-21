from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.platform_paths import (
    get_default_scan_roots,
    get_scan_roots,
    is_root_dir,
    is_windows,
)


def test_is_root_dir():
    assert is_root_dir(Path("/")) is True
    assert is_root_dir(Path.home()) is False


def test_get_default_scan_roots_macos(tmp_path: Path):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    docs = tmp_path / "Documents"
    docs.mkdir()

    with (
        patch("app.services.platform_paths.is_windows", return_value=False),
        patch("os.name", "posix"),
    ):
        roots = get_default_scan_roots(home=tmp_path)

    assert desk.resolve() in roots
    assert docs.resolve() in roots


def test_get_default_scan_roots_windows(tmp_path: Path):
    desk = tmp_path / "Desktop"
    desk.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    onedrive_desk = tmp_path / "OneDrive" / "Desktop"
    onedrive_desk.mkdir(parents=True)

    with (
        patch("app.services.platform_paths.is_windows", return_value=True),
        patch("os.name", "nt"),
    ):
        roots = get_default_scan_roots(home=tmp_path)

    assert desk.resolve() in roots
    assert source.resolve() in roots
    assert onedrive_desk.resolve() in roots


def test_get_scan_roots_custom_valid(tmp_path: Path):
    custom = tmp_path / "my_custom_code"
    custom.mkdir()

    roots = get_scan_roots(configured_root=str(custom), home=tmp_path)
    assert len(roots) == 1
    assert roots[0] == custom.resolve()


def test_get_scan_roots_custom_invalid_or_missing(tmp_path: Path):
    desk = tmp_path / "Desktop"
    desk.mkdir()

    # If configured path does not exist, fall back to default roots.
    roots = get_scan_roots(configured_root=str(tmp_path / "missing_folder"), home=tmp_path)
    assert desk.resolve() in roots


def test_get_scan_roots_rejects_filesystem_root(tmp_path: Path):
    desk = tmp_path / "Desktop"
    desk.mkdir()

    # Root of filesystem is rejected as an unsafe scan root.
    roots = get_scan_roots(configured_root="/", home=tmp_path)
    assert Path("/").resolve() not in roots
    assert desk.resolve() in roots
