import tomllib
from pathlib import Path


def test_windows_distribution_manifest_is_present() -> None:
    root = Path(__file__).parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    script = (root / "build_windows.bat").read_text(encoding="utf-8")

    assert (root / "LICENSE").is_file()
    assert (root / "resources" / "sample_model" / ".frc-architecture" / "model.json").is_file()
    assert (root / "assets" / "ArchitectureModelLogo.ico").is_file()
    assert "pyinstaller" in " ".join(metadata["project"]["optional-dependencies"]["build"])
    assert "PyInstaller" in script
    assert "tree_sitter_java" in script
    assert "--collect-all PySide6" not in script
    assert "--windowed" in script
    assert "--icon" in script
    assert "ArchitectureModelLogo.ico" in script
    assert "%CD%\\resources;resources" in script
    assert "%CD%\\LICENSE;." in script
    assert "copy /Y" in script


def test_windows_release_script_matches_portable_teammate_distribution() -> None:
    root = Path(__file__).parents[2]
    script = (root / "build_release.bat").read_text(encoding="utf-8")

    assert "call build_windows.bat" in script
    assert "Compress-Archive" in script
    assert "FRC-Architecture-Modeler_" in script
