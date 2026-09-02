# FRC Architecture Modeler — Project Plan

## 1. Product direction

Build a local-first desktop application that lets an FRC team design a command-based robot architecture, import the architecture implemented in robot code, compare the two, and export a precise Markdown change request for an AI coding tool.

The first supported code target should be **Java/WPILib command-based projects**. The architecture model itself should be language-neutral so C++ and RobotPy importers can be added later without changing the UI or saved-file format.

The central product rule is:

> User-authored design intent and code-derived facts are separate layers. Refreshing code must never overwrite the design.

This makes the tool useful before code exists, while code is being implemented, and after an AI or student changes the robot project.

### Primary workflows

1. **Design first** — create subsystems and commands, document them, connect their relationships, and export the proposed architecture before robot code exists.
2. **Import and understand** — select an existing Gradle/WPILib project, scan it, and navigate commands, subsystems, devices, triggers, lifecycle methods, command compositions, and source code.
3. **Reconcile** — see which design elements match code, differ from code, exist only in the design, or exist only in code; manually resolve ambiguous matches.
4. **Propose a change** — edit the design layer, review the semantic diff, and export an implementation-ready Markdown brief.
5. **Confirm a change** — refresh after code is changed and verify that the design/code differences have closed.

### MVP non-goals

- Editing or generating Java files directly.
- Compiling, deploying, or controlling a robot.
- Full Java type resolution equivalent to an IDE.
- Runtime telemetry or command scheduler visualization.
- C++ and RobotPy parsing in the first release.
- Cloud storage or automatic transmission of robot code to an AI service.

## 2. Recommended technical approach

Use a Python desktop application with:

- **PySide6 / Qt 6** for the application shell, responsive panels, dialogs, source viewer, and graphics scene.
- **QGraphicsScene/QGraphicsView** for the architecture canvas and command flow diagrams.
- **Tree-sitter with the Java grammar** for tolerant, source-position-preserving Java parsing.
- Python dataclasses or Pydantic-style validated domain objects behind repository interfaces.
- JSON for versioned model storage and Markdown for human/AI export.
- pytest plus Qt test utilities for automated tests.
- PyInstaller or Nuitka for a later Windows distribution build.

PySide6 is preferable to beginning a new project on PyQt5 because it is the official Qt 6 Python binding and permits an LGPL-based distribution when its obligations are followed. The PyQt5 code in `StrategySimulation` is still useful as a design reference; small utilities can be ported deliberately rather than making the new project depend on that repository.

Tree-sitter is a good first parser because it gives a concrete syntax tree and preserves useful structure and source ranges even when a file has errors. Static-analysis rules will sit above it. Keep the parser behind an importer interface so a JavaParser/JDT helper can be added later if cross-file symbol resolution becomes the limiting factor.

### Code worth borrowing from StrategySimulation

- The shared theme/palette/QSS pattern in `gui_utils/theme.py`.
- Pan, zoom, scene, node, and edge interaction patterns in `gui_utils/strategy_graph.py`.
- The wrapping layout behavior in `gui_utils/flow_layout.py`.
- Existing testing and Windows-launch/packaging conventions where applicable.

Do not import `StrategySimulation` as a runtime dependency. Copy or port only clearly reusable, generic utilities so both products remain independently distributable.

## 3. User experience specification

### Main window

The top toolbar should contain:

- Open Model
- Connect Robot Project
- Refresh Code
- New Command
- New Subsystem
- Compare/Review Changes
- Export Architecture
- Export AI Change Request
- Search/filter
- Legend and diagnostics

The status bar should show the connected project, last scan time, source revision if Git is available, parse warning count, and unsaved-model state.

### Architecture panel

Use one scrollable, zoomable canvas with three visual regions:

- A narrow minimized-items tray on the left, divided into Commands and Subsystems.
- Commands in the upper region.
- Subsystems in the lower region.

The initial layout should be deterministic and automatic. Users can drag blocks and persist their preferred positions. Auto-layout should be available as an explicit command and must not silently replace manual positioning.

Command-to-subsystem connections render behind blocks as faint curved lines. Selecting either endpoint makes that block's connected lines solid and brighter and dims unrelated elements. Hovering a line should explain the evidence for the relationship, such as `addRequirements(drive)` or `Commands.runOnce(..., intake)`.

Useful canvas controls that should be included even in the MVP:

- Pan, zoom, zoom-to-fit, and reset layout.
- Search by name, description, trigger, device, or status.
- Filters for matched, changed, design-only, code-only, and unresolved elements.
- Minimize/restore without deleting an element.
- A visible legend for all status colors and line styles.

### Command block

Collapsed command blocks show:

- Command name.
- Short effective description.
- Trigger badges at the bottom, including controller and activation behavior, for example `Driver X · on press` or `Operator RT · while held`.
- A small status badge and parse-confidence indicator when relevant.

Single-click selects. Double-click opens command details.

Command details contain:

- Identity, status, source location, and design/code comparison.
- Inputs/constructor parameters at the top.
- Requirements and related subsystems.
- Triggers and default-command/auto registration information.
- A lifecycle or composition diagram.
- Diagnostics and unresolved references.

For a conventional command class, the diagram is:

`Start → initialize → execute → isFinished? → No: execute / Yes: end`

Include `end(interrupted)` as the final phase, not merely a generic end block. Show absent overrides as inherited WPILib behavior. Each phase block displays its JavaDoc or a compact generated summary; double-clicking opens a read-only source dialog at that method.

Not every WPILib command has those four explicit methods. Use the most truthful visualization for each form:

- `Commands.runOnce` / `InstantCommand`: one action, then finish.
- `run`, `runEnd`, `startEnd`, or `FunctionalCommand`: map supplied lambdas to lifecycle phases.
- Sequential, parallel, race, and deadline groups: render a composition graph with sequence/parallel semantics.
- Decorators such as `andThen`, `alongWith`, `withTimeout`, `until`, `onlyIf`, and `deadlineFor`: retain them as semantic nodes or annotations.
- PathPlanner/autonomous wrappers: show a named external action when their internals cannot be resolved.

### Subsystem block

Collapsed subsystem blocks show:

- Subsystem name.
- Effective description.
- Device rows with a device-type icon and a human-readable name.
- Status and confidence badges.

Devices include motor controllers, encoders, gyros/IMUs, cameras, pneumatics, digital/analog inputs, addressable LEDs, and an `Unknown/custom device` fallback. When the code uses an IO abstraction, show logical devices on the subsystem and allow the details view to show REAL/SIM/REPLAY implementations separately.

Double-click opens a read-only code view in the details panel (or compact-screen dialog) with a file selector when the subsystem spans a facade, IO interface, and multiple implementations.

### Original versus proposed text

Description editing must never modify source code. The details editor shows:

- **From code** — read-only JavaDoc/comment-derived text and its source location.
- **Design/proposed** — editable text stored in the architecture model.
- **Effective** — the proposed text when present, otherwise the code text.

The same layered presentation should be used for names, devices, relationships, triggers, lifecycle intent, and other fields where design and code can differ. A user can explicitly choose “adopt from code” or “revert design override” per field.

### Responsive behavior

- At a usable content width of roughly 1280 px or greater, display a persistent resizable details panel on the right using a splitter or dock.
- Below that threshold, hide the dock and open details in a non-modal sheet/dialog over the canvas.
- Clicking outside a compact-screen details sheet dismisses it only when there are no unsaved edits. With unsaved edits, require Save or Discard.
- Remember panel width, window geometry, and display mode, but recalculate when monitors change.

### Voltage dark theme

Base the theme on the logo's dominant colors:

- Voltage yellow: approximately `#FFE800` — primary actions, design intent, selected highlights.
- Voltage blue: approximately `#0429D2` — imported-code accents and links.
- Near-black: window and canvas backgrounds.
- Off-white: primary text.
- Muted gray-blue: inactive text and faint relationships.

Status color must never be the only signal. Pair every color with an icon, badge text, border style, or hatch pattern. Suggested semantics:

- Matched: green check / solid border.
- Modified: amber delta / double border.
- Design-only: yellow plus / dashed border.
- Code-only: blue import arrow / dotted border.
- Ambiguous or parse warning: magenta/red question or warning icon.

## 4. Architecture model and persistence

### Store intent, evidence, and presentation separately

Use a small sidecar directory, normally committed with the robot project:

```text
.frc-architecture/
  model.json              # user-authored design intent and schema version
  bindings.json           # accepted links to code symbols and scan baseline
  layout.json             # positions, minimized state, zoom, and UI preferences
  exports/
    architecture.md       # optional generated artifact
    change-request.md     # optional generated artifact
```

Allow the user to save this directory elsewhere when they do not want to modify the robot repository. Paths inside the model should be relative to the model directory or robot root; do not persist a machine-specific absolute path as the only locator.

Splitting these files reduces noisy merge conflicts: semantic design edits do not churn canvas coordinates, and UI changes do not appear as architecture changes.

### Three logical layers

1. **Design intent** — editable entities and values authored by the user.
2. **Accepted code baseline** — the last scan/mapping the user accepted, used for stable matching and change history.
3. **Current code scan** — freshly extracted facts, held in memory and safely regenerable.

Comparison primarily asks “Does current code implement current design?” The accepted baseline helps identify source-side renames, additions, and deletions between refreshes.

Never store full source files in the model. Store relative source paths, symbol signatures, source spans, and content hashes. Read actual code from the connected project when requested.

### Core domain objects

Use UUIDs for model identities and separate them from code symbol identities.

- `ArchitectureProject`: schema version, product version, project metadata, language/importer configuration, and roots.
- `Command`: design fields, code binding, parameters/inputs, triggers, requirements, lifecycle/composition, and provenance.
- `Subsystem`: design fields, code binding, device ownership, methods/files, and provenance.
- `Device`: type, display name, vendor/class, ports or CAN IDs when statically known, mode, and confidence.
- `TriggerBinding`: controller/trigger expression, activation behavior, command, source anchor, and confidence.
- `Relationship`: typed edge such as `requires`, `calls`, `contains`, `triggers`, or `owns_device`.
- `SourceAnchor`: relative path, qualified symbol, signature, start/end positions, and source hash.
- `FieldValue`: design value, scanned value, comparison state, evidence, and confidence.
- `Diagnostic`: severity, message, source anchor, and suggested resolution.
- `LayoutState`: position, size, minimized state, grouping, and viewport settings.

Every extracted fact should have provenance and confidence:

- `exact`: directly declared, such as `addRequirements(drive)`.
- `inferred`: reached through a factory method or IO implementation.
- `unresolved`: plausible relationship that could not be bound to one symbol.

### Compatibility and migration

- Include `schemaVersion` in every persisted file.
- Validate on load and write atomically through a temporary file plus replace.
- Keep explicit, tested migrations between schema versions.
- Preserve unknown fields when practical so a newer model is not silently damaged by an older application.
- Autosave recoverable drafts, but require an explicit Save for the committed model.

## 5. Java/WPILib importer

### Scan pipeline

1. Detect a Gradle/WPILib project and Java source roots.
2. Exclude `.gradle`, `build`, `bin`, generated sources, vendordeps, and backups by default.
3. Parse Java files and record syntax errors without aborting the whole scan.
4. Build symbol tables for packages, imports, types, fields, constructors, methods, and local aliases.
5. Run WPILib-specific extraction passes.
6. Resolve cross-file references and command compositions as far as static evidence permits.
7. Normalize facts into the language-neutral domain model.
8. Reconcile the scan with existing design entities and bindings.
9. Present a refresh review before accepting mappings that are destructive or ambiguous.

Run parsing in a worker thread/process so the Qt event loop stays responsive. A scan should be cancellable and should publish progress by files parsed and extraction phase.

### Extraction rules

**Subsystems**

- Classes extending `SubsystemBase` or implementing `Subsystem`.
- Named subsystem instances in `RobotContainer` or equivalent containers.
- IO facade/interface/REAL/SIM patterns linked by constructor injection.

**Commands**

- Classes extending `Command` or `CommandBase`.
- Methods returning `Command`.
- `Commands.*` factories and subsystem `run`/`runOnce` helpers.
- `InstantCommand`, `FunctionalCommand`, and command-group constructors.
- Chained command decorators and nested compositions.
- Autonomous builders and registered/named commands.

**Requirements and relationships**

- `addRequirements(...)` calls.
- Requirement arguments to command constructors/factories.
- The implicit subsystem requirement of subsystem `run`/`runOnce` helpers.
- The union of children for command groups.
- Calls into a known subsystem when no explicit scheduler requirement is present; flag this as inferred and potentially suspicious rather than treating it as equivalent to `requires`.

**Triggers**

- `onTrue`, `onFalse`, `whileTrue`, `whileFalse`, `toggleOnTrue`, and `toggleOnFalse`.
- Default commands and autonomous/dashboard registrations.
- Controller aliases, HID port when statically available, trigger composition, and debounce decorators.
- Human-readable normalization such as `kDriveController.rightTrigger()` → `Driver right trigger` when a controller role can be inferred or configured.

**Lifecycle and documentation**

- Constructor parameters and stored suppliers.
- `initialize`, `execute`, `isFinished`, and `end` overrides.
- JavaDoc immediately attached to classes/methods; fall back to nearby comments only with lower confidence.
- Exact source slices for the read-only code popup.

**Devices**

- A configurable catalog of common WPILib, REV, CTRE, PhotonVision, and pneumatics types.
- Constructor arguments for CAN IDs, channels, buses, and names when they are constant expressions.
- Constants traced one or two safe symbol hops; preserve unresolved expressions rather than guessing values.
- Hardware behind IO implementations mapped back to its logical subsystem and tagged by REAL/SIM/REPLAY mode.

### Reconciliation algorithm

Match in decreasing confidence:

1. Existing explicit binding to the same qualified symbol/signature.
2. Exact qualified symbol and kind.
3. Exact normalized name within the expected package/container.
4. Strong structural similarity: same kind, requirements/devices, trigger context, and nearby source path.
5. Manual choice.

Never silently apply a fuzzy rename. Present suggested matches with evidence and let the user confirm. Once confirmed, persist the binding so later refreshes remain stable.

Element statuses are `matched`, `modified`, `design_only`, `code_only`, `ambiguous`, and `scan_error`. Field-level differences roll up into the element status.

Refresh should be transactional: parse into a new snapshot, compare it, and only replace the accepted baseline after the user accepts the refresh. A failed scan leaves the previous usable view intact.

## 6. Export formats

### Architecture Markdown

Generate deterministic Markdown suitable for Git review and human onboarding:

1. Project and generation metadata.
2. Architecture overview and legend.
3. Subsystems, devices, responsibilities, and source status.
4. Commands, descriptions, inputs, lifecycle/composition, requirements, and triggers.
5. Relationship matrix.
6. Design/code discrepancy table.
7. Unresolved parser diagnostics and assumptions.

Sort semantically by explicit user order, then stable name. Do not include canvas coordinates.

### AI change-request Markdown

Generate a narrower implementation brief from the design-to-code delta:

- Objective and intended behavior.
- Robot project root and relevant relative files.
- Commands/subsystems to add, modify, remove, or rename.
- Exact current-state evidence with symbol names and source locations.
- Desired triggers, requirements, devices, lifecycle behavior, and command composition.
- Constraints: WPILib conventions, existing IO abstraction, simulation/replay compatibility, and “do not edit” boundaries.
- Acceptance criteria expressed as observable architecture facts.
- Validation commands suggested from the Gradle project, without claiming they have already passed.
- Uncertainties requiring the coding model to inspect rather than assume.

The export should be self-contained but should not paste whole source files. Include small source excerpts only when necessary and user-approved. The tool itself remains local and does not call an AI service in the MVP.

## 7. Internal component architecture

```text
src/frc_arch_modeler/
  app.py
  domain/
    model.py
    comparison.py
    diagnostics.py
  persistence/
    project_store.py
    migrations.py
    schemas/
  importers/
    base.py
    java/
      parser.py
      symbols.py
      wpilib_extractors.py
      device_catalog.py
      reconcile.py
  services/
    project_service.py
    refresh_service.py
    export_service.py
  ui/
    main_window.py
    theme.py
    architecture_scene.py
    command_flow_scene.py
    blocks.py
    edges.py
    details/
    dialogs/
  resources/
    icons/
    voltage_logo.png
tests/
  unit/
  integration/
  gui/
  fixtures/
docs/
```

Dependencies point inward: UI and importers depend on domain interfaces; domain code does not import Qt or Tree-sitter. This makes parser tests fast and allows future CLI/export use without launching a GUI.

Use a command/undo stack for every design edit and layout move. It gives Ctrl+Z/Ctrl+Y, simplifies dirty-state handling, and creates a clean future path to an edit history.

## 8. Delivery roadmap

Estimates below are person-weeks for one experienced developer and are intentionally ranges, not calendar commitments.

### Phase 0 — Spikes and fixtures (0.5–1 week)

- Establish packaging, linting, tests, and basic Qt shell.
- Prove Tree-sitter parsing against representative files from `TyRapXXVI_2`.
- Build a checked-in, minimal anonymized fixture rather than making tests depend on an external absolute path.
- Inventory command, subsystem, trigger, IO, and composition patterns in the reference project.
- Confirm PySide6 Windows packaging and startup time.

**Exit:** a headless scan prints a normalized inventory and a packaged empty Qt window starts on Windows.

### Phase 1 — Design-only vertical slice (1.5–2 weeks)

- Implement domain model, validation, migrations, and atomic persistence.
- Create/open/save model.
- Architecture canvas, command/subsystem blocks, edges, selection, dragging, minimization, and auto-layout.
- Details editing with undo/redo.
- Responsive dock/dialog behavior.
- Voltage theme and initial device icons.
- Architecture Markdown export.

**Exit:** a team can design and save an architecture before code exists, reopen it without loss, and export useful Markdown.

### Phase 2 — Java import vertical slice (2–3 weeks)

- Java syntax/symbol index.
- Subsystem and traditional command-class extraction.
- Lifecycle methods, JavaDoc, source anchors, and read-only code viewer.
- Command-returning methods, basic factories, requirements, triggers, and devices.
- Background/cancellable refresh with diagnostics.

**Exit:** the reference robot project produces a navigable architecture without crashing, and every displayed fact links to source evidence.

### Phase 3 — Diff and reconciliation (1.5–2 weeks)

- Design/code layered field editor.
- Matching, manual binding, status roll-up, refresh review, and accepted baseline.
- Code-only/design-only/modified filters and relationship evidence.
- AI change-request export.

**Exit:** edit a design, export the difference, change a fixture project, refresh, and confirm that matching differences close without losing design intent.

### Phase 4 — Complex WPILib semantics and hardening (1.5–3 weeks)

- Functional commands, decorators, groups, autos, IO modes, and device tracing.
- Performance work for large projects.
- Accessibility, keyboard navigation, recovery, schema migration, and corrupted-file handling.
- Installer, bundled licenses, release checklist, and user documentation.

**Exit:** representative FRC code idioms have golden tests, a Windows build can be installed by a student, and failure modes produce actionable diagnostics.

### Future capability — System behavior diagrams (post-MVP)

Add an optional behavior-diagram workspace alongside the static architecture canvas.
It should model authored scenarios, states, events, and command/subsystem interactions
without pretending to be a full SysML implementation. The initial notation can be
SysML-inspired: activity flows for operator and autonomous scenarios, plus state
transitions for high-level robot modes. These diagrams should reference the same
commands, subsystems, triggers, and typed relationships already stored in the
architecture model, while remaining a separately editable design layer. Importing
Java code may eventually provide evidence links, but must not overwrite authored
behavior intent.

**Expected MVP:** about 7–11 person-weeks. A useful design-only prototype arrives much earlier at the end of Phase 1.

## 9. Test and validation strategy

### Unit tests

- Model validation, serialization, migration, and unknown-field behavior.
- Field-level diff and status roll-up.
- Stable identifiers and reconciliation scoring.
- Markdown determinism and escaping.
- Tree-sitter queries and each WPILib extraction rule.
- Device catalog and constant-expression handling.

### Golden integration tests

Maintain small Java fixtures for:

- Lifecycle command class.
- Command factory inside a subsystem.
- Trigger chains and controller aliases.
- Sequential/parallel/race/deadline compositions.
- Functional command lambdas.
- Default and autonomous commands.
- IO abstraction with REAL/SIM/REPLAY devices.
- Syntax errors and unresolved types.
- Rename, deletion, and ambiguous matching.

Store expected normalized JSON and expected Markdown. Review golden changes intentionally.

### Reference-project tests

Use `C:\Users\josep\Documents\TyRapXXVI_2` as a local exploratory/acceptance target, not as a mandatory CI dependency. Initial quality gates should include:

- Discover all seven `SubsystemBase` classes currently present.
- Recognize both command subclasses and command-returning factory methods.
- Extract the bindings in `RobotContainer`, including `onTrue`, `onFalse`, and `whileTrue` chains.
- Represent nested sequential/parallel autonomous routines without flattening away their semantics.
- Trace IO implementations to logical subsystems and distinguish simulation hardware.
- Produce diagnostics instead of dropping unresolved constructs silently.

### GUI tests

- Selection emphasizes only relevant connections.
- Minimize/restore and manual positions survive reload.
- Details dock switches to compact dialog at the breakpoint.
- Unsaved edits are protected on outside-click, refresh, close, and project switch.
- Source navigation opens the correct file and method.
- Zoom/pan and large graphs remain interactive.
- Status remains distinguishable under common color-vision deficiencies.

### Performance targets

- First scan of a typical FRC project: under 3 seconds on a normal team laptop.
- Unchanged refresh: under 1 second by hashing files and reusing parse results.
- Architecture interaction: 60 Hz-feeling pan/zoom for roughly 200 blocks and 500 edges.
- All parser work off the UI thread; cancellation feedback within 250 ms.

Treat these as targets to measure in Phase 2, not assumptions.

## 10. Principal risks and mitigations

### Java semantics exceed a syntax parser

Factory methods, aliases, lambdas, inheritance, and external libraries make exact resolution difficult. Preserve uncertainty, attach evidence, support manual binding, and keep the importer replaceable. Add richer symbol resolution only where measured failures justify it.

### The word “command” is ambiguous

A class, factory method, inline command, composed command, trigger-bound instance, and autonomous routine are related but not identical. Give each an explicit internal subtype while presenting a unified Command concept in the UI.

### Hardware ownership is obscured by IO abstraction

Model logical subsystem ownership separately from implementation devices and robot mode. Never imply that simulation objects are physical hardware.

### Refresh could destroy authored work

Use separate layers, transactional scans, accepted baselines, atomic saves, autosave recovery, and a refresh review for ambiguous/destructive changes.

### Dense graphs become unreadable

Use top/bottom semantic regions, minimization, filtering, selection focus, edge bundling only if needed, and a deterministic auto-layout. Do not attempt to show every method call as an architecture edge.

### AI export becomes vague or overlarge

Generate from the semantic delta, include source anchors and acceptance criteria, and omit unchanged elements and full source copies.

### Licensing and asset reuse

Record the license of the application, Qt distribution obligations, Tree-sitter grammar, icons, and copied internal utilities. Obtain explicit permission/confirm ownership before shipping the Voltage logo in a public release.

## 11. Definition of MVP success

The MVP is successful when a student can:

1. Create a new model with commands and subsystems before code exists.
2. Connect it to the provided Java robot project and refresh without losing design edits.
3. See code-derived commands, command factories, subsystems, devices, triggers, requirements, lifecycle/composition, and source evidence.
4. Distinguish matched, changed, design-only, code-only, and ambiguous elements without relying on color alone.
5. Open the exact source for a command phase or subsystem in read-only mode.
6. Edit proposed architecture fields, undo the edit, save/reopen, and preserve layout/minimized state.
7. Export deterministic architecture Markdown and a focused AI implementation brief.
8. Refresh after a code change and verify that implemented differences become matched.
9. Complete these tasks on both a large monitor and a laptop-size display.

## Additional Features

FRC project scope is small enough to capture in one structure diagram, but multiple activity diagrams will be needed. When Behavior tab is active, replace the code inventory with a model browser where we can create multiple named activity diagrams. We should be able to have activity diagrams at the root/top level of the model but also tied to specific commands (tree view)

## Controlls Tab

Add a new tab that shows the Xbox Driver and Manipulator controller layouts (button mapping). Use the controller png under assets, which has red lines pointing to the different buttons. Like the other functions, we should have a design (able to write the desired controls) separate from logic that parses the actual implemented controls from the code, with the ability to show both a button's planned/designed function and the function it currently maps to in the code. Ideally we would be able to jump/link from the control to the relevant activity diagram or trigger in the structure view

## 12. Decisions to confirm after the first spike

The plan can proceed with the following defaults; they do not need to block Phase 0:

- Product name: working name **FRC Architecture Modeler**.
- First platform: Windows, with cross-platform-safe code.
- First language/importer: Java/WPILib.
- Project storage: `.frc-architecture/` beside the robot code, with an external-location option.
- Model editing does not modify Java code.
- AI integration is Markdown export only in the MVP.
- Import uncertainty is visible and user-resolvable, never hidden.

The first spike should return with evidence on only three possible architecture-changing questions:

1. Is Tree-sitter plus lightweight symbol resolution sufficient for at least 90% of the reference project's meaningful command/subsystem relationships?
2. Does porting the useful StrategySimulation Qt patterns to PySide6 take less effort than retaining PyQt5 for the first release?
3. Should autonomous routines appear in the main command region by default, or in a separately filterable lane?

## References

- [WPILib: Binding Commands to Triggers](https://docs.wpilib.org/en/latest/docs/software/commandbased/commands-v2/binding-commands-to-triggers.html)
- [WPILib Java API: Subsystem](https://github.wpilib.org/allwpilib/docs/release/java/edu/wpi/first/wpilibj2/command/Subsystem.html)
- [Qt for Python: QGraphicsView](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html)
- [Qt licensing](https://doc.qt.io/qt-6/licensing.html)
- [Tree-sitter: Using parsers](https://tree-sitter.github.io/tree-sitter/using-parsers/)
