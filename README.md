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

For new users, double-click [run.bat](C:\Users\josep\Documents\ArchitectureModel\run.bat) in File Explorer. It launches from the correct folder, uses the isolated runtime,
and leaves an error message visible if that runtime is unavailable.

```powershell
.\run.bat
```

Create a model, add a command and subsystem, optionally select the command to
edit its description, then use **Save Model**. The selected folder receives:

```text
.frc-architecture/
  model.json
  layout.json
  exports/architecture.md
```

## Current import and comparison workflow

1. Use **Connect Robot Project** to choose a Java/WPILib Gradle project.
2. Inspect imported commands, subsystems, factories, lifecycle methods, triggers,
   and devices in **Code Inventory**; double-click an entry to open its source.
3. Use **Compare Changes** to show unambiguous exact matches in green on the canvas.
4. Use **Accept Matches** only when you want those source bindings saved with the model.
5. Use **Export AI Change Request** to write a focused Markdown implementation brief.

Imported facts are dotted and regenerated on Refresh Code; design intent remains
solid and is never overwritten by a scan.

## Verify

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& .\.runtime-env\python.exe -m pytest --basetemp .pytest-tmp
& .\.runtime-env\python.exe -m ruff check .
```
