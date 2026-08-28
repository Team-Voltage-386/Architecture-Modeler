import tomllib
from pathlib import Path


def test_windows_distribution_manifest_is_present() -> None:
    root = Path(__file__).parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    script = (root / "build_windows.bat").read_text(encoding="utf-8")

    assert (root / "LICENSE").is_file()
    assert "pyinstaller" in " ".join(metadata["project"]["optional-dependencies"]["build"])
    assert "PyInstaller" in script
    assert "tree_sitter_java" in script
    assert "--windowed" in script
