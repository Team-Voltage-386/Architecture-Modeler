# FRC Architecture Modeler

A local-first desktop tool for designing a command-based FRC robot architecture,
importing Java/WPILib code facts, reconciling the two, and exporting Markdown
architecture and implementation-change briefs.

The implementation roadmap is in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Current status

The current MVP workbench supports both design and import workflows. Create
commands, subsystems, requirements, devices, and trigger bindings; edit proposed
names and descriptions with undo/redo; save independent model/layout state; and
generate deterministic Architecture Markdown. Java/WPILib Gradle projects can be
scanned in the background, reviewed as imported facts, reconciled with the design,
and exported as a focused AI change request. The importer is intentionally
conservative: it retains source evidence and diagnostics instead of guessing at
unresolved Java semantics.

## Run on Windows

This workspace includes an isolated `.runtime-env` Conda environment, created to
avoid a conflicting Qt DLL in the base Anaconda installation.

For new users, double-click [run.bat](C:\Users\josep\Documents\ArchitectureModel\run.bat) in File Explorer. It launches from the correct folder, uses the isolated runtime,
and leaves an error message visible if that runtime is unavailable.

```powershell
.\run.bat
```

Create a model, add commands and subsystems, then use **New Device** and **New
Trigger** to record proposed hardware and controller bindings. Select a command
to edit its proposed name, description, and required subsystems, then use **Save
Model**. The selected folder receives:

```text
.frc-architecture/
  model.json
  bindings.json           # accepted/manual design-to-code mappings
  layout.json
  draft.json              # recoverable only; cleared after an explicit Save
  exports/architecture.md
```

## Current import and comparison workflow

1. Use **Connect Robot Project** to choose a Java/WPILib Gradle project. The
   toolbar scan runs in the background; use **Cancel Scan** if needed.
2. Inspect imported commands, subsystems, factories, lifecycle methods, triggers,
   devices, and inline command forms/groups in **Code Inventory**; double-click an
   entry or select an imported canvas block to inspect its read-only source evidence.
   Imported command details show a lifecycle flow and explicitly label inherited
   WPILib phases. Hardware constants are resolved across simple Java constant files
   when safe, while original expressions remain visible as evidence.
   Inline command forms and groups stay in **Code Inventory** by default to keep
   the architecture canvas readable; choose **Show Command Forms** when you need
   to inspect those forms directly on the canvas.
3. Use **Compare Changes** to show matched, modified, design-only, code-only, and
   unresolved states. Status labels and border styles supplement the colors; use
   the toolbar state buttons to filter dense canvases.
4. Select one design block and one same-kind imported block, then choose
   **Bind Selected** to explicitly resolve a rename or ambiguous mapping. Use
   **Accept Matches** only when you want suggested bindings saved with the model.
5. Use **Export Architecture** for design and imported hardware/control evidence,
   or **Export AI Change Request** for a focused implementation brief containing
   proposed devices and triggers.

At narrower widths, double-click a selected canvas block to open the compact
non-modal details sheet. A saved model receives an atomic `draft.json` after an
edit; reopening offers to recover a differing draft, while explicit Save clears it.

Keyboard basics: `Ctrl+N`, `Ctrl+O`, and `Ctrl+S` create/open/save models;
`F5` refreshes code; `Ctrl+E` exports Architecture Markdown; and `Ctrl+F`
focuses the evidence search field.

Imported facts are dotted and regenerated on Refresh Code; design intent remains
solid and is never overwritten by a scan.

## Verify

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
& .\.runtime-env\python.exe -m pytest --basetemp .pytest-tmp
& .\.runtime-env\python.exe -m ruff check .
```

## Build a Windows distribution

Install the project build extra into the isolated runtime, then run
`build_windows.bat`. It produces a folder-based PyInstaller build at
`dist\FRC Architecture Modeler\`, including this project's MIT license.

```powershell
& .\.runtime-env\python.exe -m pip install -e ".[build]"
.\build_windows.bat
```

The build bundles Qt and the Tree-sitter Java grammar. The generated folder has
been smoke-validated for its executable, root-level MIT license, and Java grammar
payload. Review third-party distribution licenses before publishing a release.
