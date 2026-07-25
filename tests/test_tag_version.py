from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/check_tag_version.py"
SPEC = importlib.util.spec_from_file_location("check_tag_version", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
check_tag_version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_tag_version)


def write_project(root: Path, pyproject: str, source: str) -> None:
    (root / "src/agentic_blog").mkdir(parents=True)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / "src/agentic_blog/__init__.py").write_text(source, encoding="utf-8")


def test_valid_tag_matches_committed_metadata_and_static_source() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        pyproject_version = tomllib.load(stream)["project"]["version"]

    assert check_tag_version.main([f"v{pyproject_version}"]) == 0
    assert (
        check_tag_version.source_version(PROJECT_ROOT / "src/agentic_blog/__init__.py")
        == pyproject_version
    )


@pytest.mark.parametrize("tag_name", ["0.1.0", "v", "release-v0.1.0"])
def test_tag_must_use_canonical_v_prefix(tag_name: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_tag_version.main([tag_name]) == 1
    assert "canonical v<version>" in capsys.readouterr().err


def test_tag_version_mismatch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(
        tmp_path,
        '[project]\nversion = "0.1.0"\n',
        '__version__ = "0.1.0"\n',
    )
    monkeypatch.setattr(check_tag_version, "PROJECT_ROOT", tmp_path)

    assert check_tag_version.main(["v0.2.0"]) == 1


def test_pyproject_version_mismatch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(
        tmp_path,
        '[project]\nversion = "0.2.0"\n',
        '__version__ = "0.1.0"\n',
    )
    monkeypatch.setattr(check_tag_version, "PROJECT_ROOT", tmp_path)

    assert check_tag_version.main(["v0.2.0"]) == 1


def test_source_version_mismatch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(
        tmp_path,
        '[project]\nversion = "0.1.0"\n',
        '__version__ = "0.2.0"\n',
    )
    monkeypatch.setattr(check_tag_version, "PROJECT_ROOT", tmp_path)

    assert check_tag_version.main(["v0.1.0"]) == 1


@pytest.mark.parametrize(
    "pyproject",
    [
        '[project]\nname = "agentic-blog"\n',
        '[project\nversion = "0.1.0"\n',
    ],
)
def test_missing_or_malformed_pyproject_metadata_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyproject: str
) -> None:
    write_project(tmp_path, pyproject, '__version__ = "0.1.0"\n')
    monkeypatch.setattr(check_tag_version, "PROJECT_ROOT", tmp_path)

    assert check_tag_version.main(["v0.1.0"]) == 1


def test_static_source_parser_rejects_dynamic_version(tmp_path: Path) -> None:
    source = tmp_path / "__init__.py"
    source.write_text("__version__ = get_version()\n", encoding="utf-8")

    with pytest.raises(ValueError, match="static string"):
        check_tag_version.source_version(source)


def test_missing_source_metadata_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project(
        tmp_path,
        '[project]\nversion = "0.1.0"\n',
        'PACKAGE_NAME = "agentic-blog"\n',
    )
    monkeypatch.setattr(check_tag_version, "PROJECT_ROOT", tmp_path)

    assert check_tag_version.main(["v0.1.0"]) == 1
