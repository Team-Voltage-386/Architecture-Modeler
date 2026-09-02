# CLAUDE.md

## Runtime and checks

- The Python runtime for this project is `.runtime-env\python.exe`. Never use `.venv`,
  `python`, or `py`.
- Tests: `$env:QT_QPA_PLATFORM='offscreen'; .\.runtime-env\python.exe -m pytest --basetemp .pytest-tmp -q`
- Lint: `.\.runtime-env\python.exe -m ruff check .`
- The suite must be green before any change is considered done. Baseline: 175 passing.

## Architecture rules

- Dependencies point inward. `domain/` must never import Qt or any parser library.
  `ui/` and `importers/` depend on domain and services, never the reverse.
- Design intent and scanned code fact are separate layers. Every user-authored field is
  a `FieldValue(design, scanned, evidence, confidence)`. A code scan must never
  overwrite a design value. New entities get FieldValue fields from the start.
- Presentation state — positions, minimized/collapsed state, view toggles, zoom — lives
  in `layout.json` through the `layout_state()` / `render_*(..., layout)` pattern. It
  never goes in `model.json`.
- Every design edit goes through `self.undo_stack` as a `QUndoCommand` subclass. The
  existing ones are `AddDesignEntityCommand`, `RemoveDesignEntityCommand`,
  `MoveBlocksCommand`, `EditTransitionEndpointsCommand`, `RenameBehaviorDiagramCommand`
  in `ui/main_window.py`, and `EditNameCommand`, `EditDescriptionCommand`,
  `EditRequirementsCommand` in `ui/details_panel.py`.
- Any change to the saved model shape bumps `SCHEMA_VERSION` in `domain/model.py` and
  ships a tested migration in `persistence/migrations.py`. Unknown fields must keep
  round-tripping through `ArchitectureProject.unknown_fields`.
- Persisted files are written atomically: temp file plus `os.replace`, as in
  `persistence/draft_store.py`.

## Testing rules

- Unit tests go in `tests/unit/` and must not require Qt. GUI tests go in `tests/gui/`
  and use the `qapp` / `qtbot` fixtures. `tests/conftest.py` already redirects
  `Path.home()` to a temp directory for every test.
- Ship tests with every behavior change. Name tests as full sentences describing the
  behavior, matching the existing style.

## Qt gotchas that have already caused crashes here

- Use `menu.popup()`, never `menu.exec()`, for context menus.
- Never round-trip a graphics item through `QGraphicsItem.setData()`; hold references as
  plain Python attributes.
- Pass Qt enums as enum members, e.g. `Qt.AspectRatioMode.KeepAspectRatio`, never ints.
- Reset any cached list of scene items before calling `scene.clear()`.
