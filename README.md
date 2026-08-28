# FRC Architecture Modeler

A local-first desktop tool for designing a command-based FRC robot architecture,
importing Java/WPILib code facts, reconciling the two, and exporting Markdown
architecture and implementation-change briefs.

The implementation roadmap is in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Current status

The Phase 1 design-only slice is ready to test. It supports creating commands and
subsystems, requirements on the architecture canvas, description overrides with
undo/redo, separate model/layout persistence, and deterministic Architecture
Markdown export. Java/WPILib import and comparison are intentionally not yet
implemented.

## Run on Windows

This workspace includes an isolated `.runtime-env` Conda environment, created to
avoid a conflicting Qt DLL in the base Anaconda installation.

```powershell
& .\.runtime-env\python.exe -m frc_arch_modeler.app
```

Create a model, add a command and subsystem, optionally select the command to
edit its description, then use **Save Model**. The selected folder receives:

```text
.frc-architecture/
  model.json
  layout.json
  exports/architecture.md
```

## Verify

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& .\.runtime-env\python.exe -m pytest --basetemp .pytest-tmp
& .\.runtime-env\python.exe -m ruff check .
```
