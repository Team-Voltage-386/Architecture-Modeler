# Implementation Prompts

Sequential prompts for implementing the [Build Season Blueprint](https://claude.ai/code/artifact/40e744f1-ac06-4893-b66b-5ab9e45f310c)
plan. Each prompt is self-contained and assumes a fresh session.

## How to use this file

1. Do **Step 0** once. It writes a `CLAUDE.md` that every later session picks up
   automatically, which is why the prompts below can stay short.
2. Work in order. Later prompts assume earlier ones landed — the ordering is by
   dependency, not by appeal.
3. Start a **fresh session per prompt**. Paste the fenced block verbatim.
4. Commit after each prompt passes its checks. A green suite between steps is what
   makes it safe to hand the next prompt to a smaller model.

## Model recommendation legend

| | Use for |
| --- | --- |
| **Opus** | Decisions that are expensive to reverse: schema and migrations, cross-layer refactors, graph and geometry algorithms, entity identity/merge semantics, and work whose *output text* is the product (the AI brief). |
| **Sonnet** | Well-specified work inside a pattern that already exists in the repo: another dialog, another panel, another table, content and fixtures, services with obvious test cases. |

If a Sonnet step stalls or the diff starts sprawling outside the named files, stop and
re-run that prompt on Opus rather than pushing through.

---

## Step 0 — Standing context (do this once)

**Model: Sonnet** — file creation, no judgment required.

```
Create a CLAUDE.md at the root of this repository containing exactly the conventions
below, formatted as clean Markdown with short sections. Do not add anything else, do
not restate the README, and do not change any other file.

Runtime and checks
- The Python runtime for this project is `.runtime-env\python.exe`. Never use `.venv`,
  `python`, or `py`.
- Tests: `$env:QT_QPA_PLATFORM='offscreen'; .\.runtime-env\python.exe -m pytest --basetemp .pytest-tmp -q`
- Lint: `.\.runtime-env\python.exe -m ruff check .`
- The suite must be green before any change is considered done. Baseline: 175 passing.

Architecture rules
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

Testing rules
- Unit tests go in `tests/unit/` and must not require Qt. GUI tests go in `tests/gui/`
  and use the `qapp` / `qtbot` fixtures. `tests/conftest.py` already redirects
  `Path.home()` to a temp directory for every test.
- Ship tests with every behavior change. Name tests as full sentences describing the
  behavior, matching the existing style.

Qt gotchas that have already caused crashes here
- Use `menu.popup()`, never `menu.exec()`, for context menus.
- Never round-trip a graphics item through `QGraphicsItem.setData()`; hold references as
  plain Python attributes.
- Pass Qt enums as enum members, e.g. `Qt.AspectRatioMode.KeepAspectRatio`, never ints.
- Reset any cached list of scene items before calling `scene.clear()`.
```

---

# Phase 1 — Floor

Stop the tool trapping people. No new concepts.

## 1.1 One form per object instead of dialog chains

**Model: Sonnet** — replaces three known functions with a standard Qt dialog pattern.

```
In `src/frc_arch_modeler/ui/main_window.py`, creating one device costs four chained
`QInputDialog` calls (`_prompt_new_device`), a trigger costs three
(`_prompt_new_trigger`), and a relationship costs three (`_prompt_new_relationship`).
Cancelling the last one discards everything entered.

Replace all three with single-form dialogs in a new file `src/frc_arch_modeler/ui/entity_dialogs.py`:

1. `DeviceDialog` — owner subsystem (combo), name, device type (editable combo
   pre-populated from the types in `importers/java/scanner.py` DEVICE_PATTERN), mode
   (Unspecified/REAL/SIM/REPLAY).
2. `TriggerDialog` — command (combo), controller/trigger expression, activation (combo
   of the six WPILib activations already listed in `_prompt_new_trigger`).
3. `RelationshipDialog` — source (combo), target (combo, excludes the chosen source),
   type (combo: calls, contains, triggers, owns_device).

Requirements
- Each dialog takes the `ArchitectureProject` plus an optional existing entity. With an
  entity it opens pre-filled in edit mode and its accessor returns the edited values;
  without one it is a create dialog. Later steps reuse the edit mode.
- OK stays disabled until required fields are non-empty. Show the reason inline, not in
  a message box.
- Create mode gets an "Add another" button that applies the values and reopens the form
  with the same owner/command preselected and the name field cleared and focused.
- Creation still routes through the existing `add_device` / `add_trigger` /
  `add_relationship` methods so undo keeps working.

Do not touch the canvas, the details panel, or the domain model.

Done when: adding three devices to one subsystem takes one dialog visit; GUI tests cover
the pre-filled edit mode and the disabled-OK validation; suite green; ruff clean.
```

## 1.2 Make devices, triggers and relationships editable and deletable

**Model: Opus** — cascade-delete semantics and undo grouping across several collections.

```
Devices, triggers and relationships in this project can be created and never edited or
deleted. There is no removal path for any of them. Separately, `delete_selected()` in
`src/frc_arch_modeler/ui/main_window.py` refuses to delete a subsystem that owns a
device, telling the user to "Remove dependent device entries first" — an instruction the
interface cannot satisfy, so the model can reach a state with no way out.

Give the owning element's details panel management of what it owns.

1. In `src/frc_arch_modeler/ui/details_panel.py`, add owned-object lists beside the
   existing "Required subsystems" list, following that widget's established pattern:
   - Subsystem selected: its devices, with Add / Edit / Remove.
   - Command selected: its triggers, with Add / Edit / Remove.
   - Either selected: relationships where it is source or target, with Add / Edit / Remove.
   Add and Edit open the dialogs from `ui/entity_dialogs.py` (step 1.1).
2. Every mutation goes through the undo stack. Reuse `AddDesignEntityCommand` and
   `RemoveDesignEntityCommand`; add an `EditEntityFieldsCommand` for in-place edits that
   snapshots and restores the entity's `FieldValue` fields.
3. Rewrite the `delete_selected()` dependency guard. Instead of refusing, summarize what
   will go with it — "Delete Shooter and its 2 devices, 1 trigger and 1 relationship?" —
   and on confirmation remove the element and its dependents as ONE undo entry (push a
   parent `QUndoCommand` with the child removals as macro children, or use
   `undo_stack.beginMacro()` / `endMacro()`). A single Ctrl+Z must restore all of it.

Constraints: no domain model changes; no canvas changes; do not weaken the existing
guard that stops deletion of a subsystem still required by a command — that one is a
real modelling error, so keep refusing but name the commands involved.

Done when: a device can be renamed and deleted; deleting a subsystem with dependents is
one confirmable, single-undo action; GUI tests cover cascade delete plus its undo;
suite green; ruff clean.
```

## 1.3 Explain the interface in place

**Model: Sonnet** — copywriting plus mechanical wiring; no architectural decisions.

```
This application has six `setToolTip` calls in total and none of them are on a toolbar
action. All explanation lives in `_build_legend_dock` in
`src/frc_arch_modeler/ui/main_window.py` — one permanently docked QLabel of static HTML
roughly 600px wide, which already omits the Join pseudostate added after it was written.

1. Give every `QAction` created in `_build_toolbar` and `_build_behavior_toolbar` a
   `setToolTip` and a `setStatusTip`. One sentence each: what it does, and when a student
   would reach for it. Write them for someone who has never seen an FRC architecture
   model. Example for Bind Selected: "Tell the tool that this design element and this
   scanned code symbol are the same thing — use it when a rename made the automatic match
   ambiguous."
2. Replace the Legend dock with a collapsible help panel: hidden by default, toggled by
   F1 and by a "?" button at the right end of the main toolbar, with a search field that
   filters its sections. Generate the notation sections from the same data the canvas
   draws from — `RELATIONSHIP_MARKERS` in `ui/architecture_scene.py` and
   `BEHAVIOR_STATE_KINDS` in `domain/model.py` — so it can no longer drift out of date.
   Assert that coverage in a test.
3. Give each behavior palette button an icon of the shape it creates, drawn with
   `QPainter` onto a `QPixmap` by the same code paths `StateBlock.paint` uses, so the
   button and the canvas cannot disagree. "Split/Merge Bar" as a word teaches nothing.

Done when: every toolbar action has a tooltip and a status tip; the help panel is closed
on startup and the canvas gets that width back; a test fails if a relationship marker or
state kind exists with no help entry; suite green; ruff clean.
```

## 1.4 Three canvas defects

**Model: Sonnet** — small, contained, each with an obvious test.

```
Fix three defects in the canvases. They are independent; keep them as separate commits.

1. Zoom to Fit does not fit. `zoom_to_fit()` in `src/frc_arch_modeler/ui/main_window.py`
   calls `fitInView(self.scene.sceneRect(), ...)`, and `sceneRect` is the padded bounding
   box captured at render time, so content ends up small and off-centre. Fit
   `self.scene.itemsBoundingRect()` with a small margin instead. Add the same action for
   the Behavior canvas, which has none.

2. Behavior transition labels collide with blocks. `_position_transition_decorations` in
   `src/frc_arch_modeler/ui/behavior_scene.py` places each label at
   `path.pointAtPercent(0.5)`; on the default seeded Robot Modes diagram two labels land
   on top of the states they describe. Offset the label perpendicular to the segment it
   sits on, and if the label rect still intersects any `StateBlock` scene rect, try
   successive offsets along the path and to the other side, keeping the first clear
   position. `ui/edge_routing.py` already has segment/rect intersection helpers — reuse
   them, do not write new ones.

3. Subsystem blocks silently drop hardware. `ArchitectureBlock.__init__` in
   `ui/architecture_scene.py` caps detail lines with `[:3]`, so a subsystem with five
   devices displays three with no indication. Keep the cap, and when lines are dropped
   append a muted final line reading "+N more" so the block is honest about what it is
   not showing.

Done when: a test asserts no transition label rect intersects any state block rect on the
seeded diagram; a test asserts the "+2 more" line appears for a five-device subsystem; a
test asserts Zoom to Fit uses item bounds; suite green; ruff clean.
```

---

# Phase 2 — Shell

## 2.1 Decompose `main_window.py`

**Model: Opus** — a 2,200-line refactor that must not move a single observable behavior.

```
`src/frc_arch_modeler/ui/main_window.py` is 2,211 lines and owns the toolbar, both
canvases, every dialog, the code scan lifecycle, both exports, the undo stack, dirty
state and the status bar. Every planned feature lands in this file until it is split.

Split it into focused collaborators under `src/frc_arch_modeler/ui/`, with MainWindow
retained as the composition root:
- `controllers/project_controller.py` — new/open/save, dirty state, draft autosave,
  recent-model tracking, close protection.
- `controllers/scan_controller.py` — connect/refresh/cancel, worker thread lifecycle,
  compare, accept matches, bind selected.
- `controllers/canvas_controller.py` — both scenes' signal wiring, selection routing,
  layout moves, auto-layout, zoom, minimize/restore.
- `controllers/behavior_controller.py` — diagram selection, state/transition editing,
  the model browser.
- `controllers/export_controller.py` — both export paths.
- `undo_commands.py` — the five QUndoCommand classes currently defined at module top.

THE BINDING CONSTRAINT: `tests/gui/test_main_window.py` is 1,220 lines and reaches
`MainWindow` attributes and private methods directly, including `window._start_scan`,
`window._left_dock_stack`, `window._refresh_behavior_after_edit`,
`window._active_behavior_diagram`, `window._apply_requested_connection` and many more.
Every existing test must pass WITHOUT BEING EDITED. Where an implementation moves to a
controller, leave a thin delegating method or property of the same name on MainWindow.
Run the suite before you start and treat any change in the pass count as a failure of the
refactor, not of the test.

Rules: no behavior changes, no renamed public attributes, no new features, no
signature changes on anything a test touches. Do the move in several commits — one
controller at a time, suite green after each.

Done when: `main_window.py` is under roughly 600 lines, each controller is independently
readable, the 175 existing tests pass unmodified, and ruff is clean.
```

---

# Phase 3 — Hardware as objects

## 3.1 Extend the Device entity

**Model: Opus** — schema change plus migration; a mistake here damages saved models.

```
`Device` in `src/frc_arch_modeler/domain/model.py` carries name, device type, owner
subsystem and mode. Everything downstream in this plan — CAN conflict detection, power
and mass budgets, the wiring table — needs more.

1. Add these as layered `FieldValue` fields, consistent with the existing ones:
   `bus` (e.g. rio, canivore name), `address` (CAN ID or channel number as text, since
   FRC uses both), `breaker_amps`, `mass_kg`, and free-text `notes`.
2. Bump `SCHEMA_VERSION` and write the migration in `persistence/migrations.py` so an
   existing model.json at version 1 loads with the new fields empty and re-saves at the
   new version. Preserve `unknown_fields` round-tripping.
3. Extend `ProjectService.add_device` with the new optional parameters and update
   `DeviceDialog` from step 1.1 to collect them, with the numeric ones validated as
   numbers but stored as the strings FieldValue holds.
4. Include the new fields in the Architecture Markdown device lines in
   `services/export_service.py`, omitting empty ones so existing golden output only
   grows where data exists.

Constraints: do not touch canvas rendering in this step. Do not infer values from the
Java scanner in this step — that is a later, separate concern.

Done when: a version-1 model on disk opens, gains the fields, and re-saves at the new
version with nothing lost; migration has a unit test with a realistic old payload;
suite green; ruff clean.
```

## 3.2 Device blocks on their own canvas tier

**Model: Opus** — the hardest layout and interaction work in the plan.

```
Hardware is currently rendered as up to three text lines inside a subsystem block, so it
cannot be selected, moved, inspected or linked. Promote it to a real canvas object on its
own tier, without drowning a canvas that will carry twenty to forty-five devices.

In `src/frc_arch_modeler/ui/architecture_scene.py`:
1. Add a `DeviceBlock` graphics item — roughly one third the height of an
   `ArchitectureBlock`: short name, a muted type label, and a mono bus/address badge. It
   is selectable and movable; it is NOT a relationship drag source.
2. Lay devices out on a third tier below the subsystem row, grouped under their owner.
   Connect each to its owner with the composition notation this file already defines and
   never uses for hardware: `RELATIONSHIP_MARKERS["owns_device"]` — a filled diamond at
   the subsystem end.
3. Three view states, cycled by a toolbar action and persisted per model in `layout.json`
   through the existing `layout_state()` mechanism:
   - `hidden` — as today, minus the text lines.
   - `grouped` (default) — no device blocks; each subsystem block shows a "N devices"
     chip that expands just that subsystem when clicked.
   - `expanded` — every device block visible.
   Per-subsystem expansion state also persists.
4. Selecting a device shows it in the details panel using the editing UI from step 1.2.
5. Devices participate in search and in the status filters like any other block.

Constraints: the default view must leave a five-subsystem robot looking no busier than it
does today. Do not change the Device domain model here. Keep the two existing rows where
they are — this is an added tier, not a re-layout.

Done when: the grouped default renders no device blocks; expanding one subsystem shows
only its devices with filled-diamond ownership edges; the view state and per-subsystem
expansion survive save and reopen; GUI tests cover all three states; suite green;
ruff clean.
```

## 3.3 Hardware table view

**Model: Sonnet** — a standard editable table over data that now exists.

```
Entering forty CAN IDs on a canvas is the wrong interaction. Add a Hardware table as a
third tab beside Structure and Behavior in `diagram_tabs`.

1. One row per device, columns: Subsystem, Name, Type, Bus, Address, Breaker (A),
   Mass (kg), Mode, Notes. Sortable by any column; grouped by subsystem by default.
2. Cells are editable in place, and every edit goes through the undo stack using the
   `EditEntityFieldsCommand` added in step 1.2.
3. Toolbar above the table: Add Device (opens `DeviceDialog`), Delete Selected, and a
   filter field.
4. Selecting a row selects the matching `DeviceBlock` on the Structure canvas, and
   vice versa, so the two views stay in sync.
5. Numeric columns right-aligned with tabular figures; empty cells render as a muted
   dash rather than blank.

Constraints: no new domain fields; no changes to canvas rendering beyond the selection
sync; reuse the existing theme rather than adding styles.

Done when: a device edited in the table updates the canvas block and undoes in one step;
selection sync works both directions; GUI tests cover editing, undo and sync;
suite green; ruff clean.
```

## 3.4 Allocation conflict detection

**Model: Sonnet** — pure logic with obvious tests, no UI judgment.

```
Now that devices carry bus and address, detect the hardware allocation errors that
actually cost FRC teams matches. Write this as a pure service so it is testable without
Qt: `src/frc_arch_modeler/services/allocation_service.py`.

Return a list of typed findings, each with a severity, a message, and the ids of the
entities involved:
1. Two devices sharing the same bus and address — the duplicate CAN ID that stops a robot
   moving on the field.
2. A device with an empty address whose type normally needs one (any CAN motor
   controller, encoder or IMU) — flag as incomplete, not as an error.
3. A device whose owner subsystem no longer exists — a model integrity error.
4. Two devices on the same PDH/PDP breaker channel.
5. Summed breaker amps exceeding a configurable total, and summed mass exceeding a
   configurable limit. Both limits are constructor parameters with documented defaults,
   because the FRC rules that set them change from season to season — do not hard-code a
   number as if it were permanent.

Surface findings as a red badge on the offending row in the Hardware table and on the
offending `DeviceBlock`; clicking the badge selects the other device in the conflict.

Constraints: no Qt import in the service; the findings shape must be reusable by the
Model Health panel in step 4.4, so design it for that consumer now.

Done when: unit tests cover every finding type including the no-conflict case; a
duplicate address is visible on both the canvas and the table; suite green; ruff clean.
```

---

# Phase 4 — Learn by using

## 4.1 Ship a sample robot

**Model: Sonnet** — content-heavy, mechanical, high value per unit of risk.

```
The application opens on an empty black canvas. A new student's first act is inventing a
subsystem name in a modal dialog. Give them something to take apart instead.

1. Add `resources/sample_model/` containing a complete, realistic and internally
   consistent FRC robot model saved in the normal sidecar format: a swerve drivetrain
   (four drive motors, four steer motors, four encoders, a gyro), intake, elevator,
   shooter and climber; commands for each with requirements set; controller triggers;
   fully allocated hardware with distinct CAN IDs, breakers and masses; and two behavior
   diagrams — the match-mode state machine and one autonomous routine.
2. Add a matching minimal Java/WPILib fixture under `tests/fixtures/java_sample/` whose
   scan reconciles against that model with a deliberate mix of outcomes: mostly matched,
   one renamed element, one design-only element and one code-only element, so the compare
   and bind workflow is explorable on day one.
3. Add `MainWindow.open_sample_model()` which copies the sample to a user-chosen writable
   location and opens it, so a student can edit freely without mutating the shipped copy.
4. Include the sample in the PyInstaller build; `tests/unit/test_distribution_files.py`
   already asserts packaged payloads — extend it.

Constraints: hand-author the sample content; do not generate it at runtime. It has to be
readable as a worked example, so name things the way a good team names things.

Done when: opening the sample and running Compare Changes against the fixture produces
all four comparison states; a unit test loads the sample and asserts it validates and
has no allocation conflicts; suite green; ruff clean.
```

## 4.2 Start screen and empty states

**Model: Sonnet** — straightforward UI over capabilities that now exist.

```
1. Add a start screen shown when no project is open, in place of the empty canvas:
   New Model · Open Model · Open Recent (using the existing `RecentModelStore`) ·
   Open the Sample Robot · Take the Tour (leave the tour button disabled until step 4.5
   lands). Keep it inside the main window as a stacked widget page — not a modal dialog —
   so it disappears the moment a project opens.
2. Give every region that can be empty a purposeful empty state instead of blankness:
   the Structure canvas with no subsystems, the Code Inventory with no scan, the details
   panel with nothing selected, the behavior diagram list, and the Hardware table. Each
   states what belongs there in one sentence and offers the button that creates it.
3. The details panel currently shows six stacked buttons, five of which do nothing in a
   design-only model. Hide the code-related actions entirely until a scan exists rather
   than showing them disabled.

Constraints: no new domain concepts; reuse existing actions rather than duplicating their
logic; the start screen must not appear when a project is already open.

Done when: launching with no project shows the start screen; opening the sample dismisses
it; GUI tests cover the empty states and the hidden-until-scanned buttons; suite green;
ruff clean.
```

## 4.3 Templates and automatic addressing

**Model: Sonnet** — data plus a small service; the automation the plan asks for.

```
Building a swerve drivetrain by hand costs thirteen device dialogs. Make it one click.

1. Add `services/template_service.py` with subsystem templates defined as data:
   Swerve Drivetrain (4 drive + 4 steer + 4 encoders + gyro), Differential Drivetrain,
   Roller Intake, Elevator, Flywheel Shooter, Winch Climber, Vision, LEDs. Each names its
   devices, sets device types, and includes a short description a student can edit.
2. Add "New Subsystem from Template" to the New toolbar group. It creates the subsystem
   and all its devices as a single undo entry.
3. Add `next_free_address(project, bus)` to the allocation service from step 3.4 and use
   it to assign addresses as templates and individual devices are created, so the tool
   proposes the next free CAN ID instead of leaving a student to keep a spreadsheet
   beside it. The proposal is always editable and never silently overwrites a value the
   user typed.
4. Add a command template that creates a command, sets its requirement to a chosen
   subsystem, and optionally adds a trigger — the three steps a student currently does as
   three unrelated actions.

Constraints: templates are plain data, not subclasses. No new domain entities.

Done when: one click produces a swerve drivetrain with thirteen correctly typed,
conflict-free devices, undone by one Ctrl+Z; unit tests cover next-free-address including
gaps and multiple buses; suite green; ruff clean.
```

## 4.4 Model Health panel

**Model: Opus** — the rule set is a design decision and the panel touches everything.

```
Build the single highest-value teaching feature in this plan: a live, clickable list of
what is wrong with the model, so the tool states the rules a mentor currently has to say
out loud.

1. Add `services/health_service.py` returning typed findings — severity, message,
   entity ids, and an optional fix action id — computed from the project alone. No Qt.
   Fold in the allocation findings from step 3.4 rather than duplicating them.
2. Rules to ship: a subsystem no command requires; a command with no requirements; a
   command with no trigger and not referenced by any behavior diagram; a device whose
   type normally needs an address and has none; duplicate addresses and breaker channels;
   a behavior diagram with no start state; a behavior state unreachable from its start; a
   transition with an empty label that is not adjacent to a start/join/sync node; an
   element whose name is still a default like "Unnamed" or "New Command"; and, once step
   5.1 lands, a requirement satisfied by nothing.
3. Add a dockable Model Health panel: findings grouped by severity, a live count badge in
   the status bar, click to select and reveal the offending element on whichever canvas
   owns it. Recompute on model change, debounced, off the paint path.
4. Where a fix is unambiguous and safe, offer it inline as an undoable action — assign
   the next free address, remove an orphaned relationship. Never auto-apply anything.

Constraints: rules live in the service and are individually unit-tested against small
constructed projects; the panel must contain no rule logic. Findings must be stable and
deterministically ordered so tests can assert on them.

Done when: every rule has a unit test proving it fires and a test proving it stays quiet
on a healthy model; the sample robot from step 4.1 reports zero findings; clicking a
finding selects the element; suite green; ruff clean.
```

## 4.5 Guided tour

**Model: Sonnet** — overlay mechanics plus scripted content.

```
Add a six-step guided tour, launched from the start screen and from Help.

Steps, each with a highlighted target widget, one sentence of instruction, and a
completion condition read from the model rather than from a click:
1. Create a subsystem (or add one from a template).
2. Give it a device, and notice the address the tool proposed.
3. Create a command and set its required subsystem.
4. Bind a controller trigger to that command.
5. Open the Behavior tab and add a transition between two states.
6. Link that transition to the command from step 3, then export the Architecture
   Markdown and look at what came out.

Implementation notes
- One translucent overlay widget over the main window with a cut-out around the target
  widget's geometry, plus a small step card. Reposition on resize and on dock changes.
- The tour observes the model; it never performs the actions for the user. If they do
  something else first, it recognizes the step as done and moves on.
- Exit at any point; remember completion in the UI preferences already stored in
  `layout.json`, so it does not reappear.
- Step 6 depends on step 6.1 of this plan. If transition-to-command linking does not yet
  exist, end the tour at step 5 and leave a clearly marked hook.

Done when: the tour runs start to finish on a new empty model, survives a window resize,
and can be exited and resumed; GUI tests drive at least the first three steps
programmatically; suite green; ruff clean.
```

## 4.6 Layered auto-layout

**Model: Opus** — a graph layout algorithm with stability requirements.

```
`auto_layout()` currently re-renders in fixed rows: commands at y=0, subsystems below,
devices ungrouped. With a hardware tier and realistic edge counts it needs a real
algorithm.

Implement layered (Sugiyama-style) layout in a new pure module
`src/frc_arch_modeler/ui/graph_layout.py`, no Qt imports, taking nodes with sizes and
typed edges and returning positions:
1. Layers by kind: triggers/controllers, commands, subsystems, devices.
2. Order within a layer by weighted median of connected nodes' positions, two sweeps each
   direction, to reduce edge crossings.
3. Horizontal packing that respects each block's real width and keeps a device group
   under its owner.
4. Deterministic: the same model must always produce the same layout, so break every tie
   on a stable key, never on set or dict iteration order.
5. Stable under small edits: adding one command must not reshuffle the whole canvas.
   Seed the ordering from current positions when they exist.

Wire it behind the existing Auto Layout action, applied through `MoveBlocksCommand` so it
is a single undoable step — auto-layout must never silently destroy manual positioning
with no way back.

Done when: unit tests assert determinism, assert crossing count does not regress on a
fixture graph, and assert that adding one node moves fewer than a quarter of the others;
Auto Layout is one Ctrl+Z; suite green; ruff clean.
```

---

# Phase 5 — Requirements

## 5.1 The requirements entity and its traces

**Model: Opus** — the MBSE backbone; its shape constrains everything after it.

```
The model has no answer to "why does this subsystem exist". Add the requirements layer.

1. In `src/frc_arch_modeler/domain/model.py` add a `Requirement` entity: `text`
   (FieldValue), `source` (FieldValue — a citation such as "2026 manual §5.4" or "drive
   team"), `priority` (must / should / could), `rationale` (FieldValue), optional
   `parent_id` for decomposition, and the standard `id` plus `code_binding`.
2. Add `satisfied_by: list[UUID]` linking a requirement to the commands and subsystems
   that satisfy it. Validate in `ArchitectureProject.__post_init__` the way relationship
   endpoints are already validated: every id must exist, and a parent chain must not
   cycle.
3. Bump `SCHEMA_VERSION`, write the migration, keep `unknown_fields` round-tripping.
4. Extend `ProjectService` with add/edit/remove and link/unlink operations.
5. Deleting an element that satisfies a requirement must not be silently allowed to
   orphan it — surface it in the same cascade dialog built in step 1.2.

Constraints: requirements are a peer layer, not a field on Subsystem. Keep them out of
the canvas entirely in this step. Every text field is a FieldValue so a future importer
can attach scanned evidence.

Done when: requirements round-trip through save/open with links intact; cycle detection
and dangling-link validation have unit tests; the migration has a unit test with a
realistic pre-requirements payload; suite green; ruff clean.
```

## 5.2 Requirements workspace

**Model: Sonnet** — follows the panel and dialog patterns now established.

```
Add the UI for the requirements layer from step 5.1.

1. A Requirements dock: a tree showing decomposition (parent requirements with children),
   with priority chips and a satisfied/unsatisfied marker on each row.
2. A requirement inspector reusing the details panel layout: text, source, priority,
   rationale, and the list of elements that satisfy it with Add / Remove.
3. Linking from the other direction: with a subsystem or command selected on the canvas,
   its details panel gains a "Satisfies" list with the same Add / Remove.
4. Both directions push undoable commands and stay in sync.
5. Selecting a requirement highlights every element that satisfies it on the Structure
   canvas and dims the rest, reusing the existing selection-emphasis mechanism rather
   than inventing a second one.

Constraints: no new domain changes; no canvas blocks for requirements — highlighting
only. Follow the existing dock and inspector conventions exactly.

Done when: a requirement can be created, decomposed, linked from both directions, and
undone; selecting it highlights its satisfiers; GUI tests cover the round trip;
suite green; ruff clean.
```

## 5.3 Coverage matrix and export

**Model: Sonnet** — reporting over a model that already holds the data.

```
Make the requirements layer pay off in artifacts.

1. Add a coverage view — requirements down the side, subsystems and commands across the
   top, a mark at each satisfying intersection, with unsatisfied rows and unjustified
   columns visually distinct. It must stay readable at thirty requirements; scroll it in
   its own container.
2. Add two Model Health rules to step 4.4's service: a requirement satisfied by nothing,
   and a subsystem or command that satisfies no requirement (informational, not an error
   — some elements are genuinely infrastructural).
3. Extend `services/export_service.py`: a Requirements section with full text, source and
   priority; a satisfaction table; and an explicit "Requirements with no implementation"
   list. Keep the output deterministic and keep escaping table cells the way
   `_cell` already does.
4. Extend `services/change_request_export.py` so each requested change cites the
   requirement it serves. An AI coding tool implementing an elevator command should be
   told the elevator exists to score in the amp.

Done when: export output is deterministic across runs and covered by a golden test; the
coverage view renders the sample robot legibly; suite green; ruff clean.
```

---

# Phase 6 — Traceability

## 6.1 Wire behavior to structure

**Model: Sonnet** — the model already supports it; this is connecting existing parts.

```
`BehaviorTransition.command_id` in `src/frc_arch_modeler/domain/model.py` is validated,
serialized, round-tripped and accepted by `ProjectService.add_behavior_transition`. No UI
in this application ever sets it. The most valuable link in the model exists only in the
file format.

1. Add an inspector for behavior states and transitions to the details panel — it
   currently says "Select a command or subsystem to inspect its details" even when a
   state is selected. Transition fields: trigger label, and a command combo that sets
   `command_id`. State fields: name, description, and a "command that runs in this state"
   reference.
2. Adding a state-level command reference needs a `command_id` on `BehaviorState`:
   add it, bump `SCHEMA_VERSION`, migrate, validate the id exists, following the same
   pattern as the transition field.
3. Show the link on the canvas: a transition bound to a command renders its label as
   `trigger / CommandName`, and a state with a command shows the command name as a muted
   second line.
4. Add two Model Health rules: a command no behavior diagram references, and a behavior
   state that runs nothing.
5. Complete step 6 of the guided tour if it was left hooked in step 4.5.

Done when: a transition can be bound to a command and the binding survives save and
reopen; both health rules have tests; suite green; ruff clean.
```

## 6.2 Behavior in the Architecture Markdown

**Model: Sonnet** — deterministic rendering, golden-tested.

```
Behavior diagrams appear in no export. Searching for "behavior" across `services/`
returns one unrelated string. Every hour a student spends on the Behavior tab is
invisible to a design review and to the coding model this tool exists to brief.

Extend `services/export_service.py` with a Behavior section:
1. One subsection per diagram, ordered by name, noting the command it is scoped to when
   `owner_command_id` is set.
2. A state table: name, kind, description, and the command it runs.
3. A transition table: source, trigger label, target, and the bound command.
4. A Mermaid `stateDiagram-v2` block per diagram so the diagram renders in GitHub and in
   any Markdown viewer. Map pseudostates honestly: start to `[*] -->`, end to `--> [*]`,
   decision to a choice state, and fork/join to the fork/join notation. Escape labels.
5. A traceability subsection listing commands referenced by behavior and commands not
   referenced by any.

Constraints: deterministic ordering everywhere; no canvas coordinates in the output; keep
using the existing `_cell` escaping.

Done when: a golden test asserts byte-identical output across runs for the sample robot,
the Mermaid block parses, and diagram order is name-stable; suite green; ruff clean.
```

## 6.3 Design-only AI change request

**Model: Opus** — the generated text *is* the product; quality of prompt output is the deliverable.

```
`export_change_request_action` is enabled only when `self.last_scan is not None`, and
`ChangeRequestExportService.render` requires a `ScanResult`. So kickoff weekend — design
finished, no robot code yet, "scaffold this for us" — is precisely when the feature
refuses to run. That is backwards, and it blocks the highest-leverage thing this tool can
do for a student team.

1. Make `scan` and `comparison` optional in `ChangeRequestExportService.render` and
   `export`. With no scan, generate a from-scratch implementation brief for the entire
   design instead of a delta. Enable the action whenever a project is open.
2. The design-only brief must contain, in this order: objective; target WPILib project
   conventions; subsystems with their hardware including bus, address, breaker and mode;
   commands with requirements, triggers, and the behavior diagrams that reference them;
   the requirements each element satisfies (step 5.3); the relationship and interface
   picture; explicit constraints; acceptance criteria expressed as observable
   architecture facts; and an explicit "what we have not decided" section drawn from
   empty fields, so the coding model asks instead of inventing.
3. Never paste source. State facts and cite anchors, as the existing delta brief does.
4. Write the output for a coding agent, not for a person: unambiguous, no marketing
   voice, every instruction checkable. Read the current `render()` first and match its
   register.
5. Add a preview dialog before writing the file — students should see and edit the brief
   before it goes to a coding tool.

Done when: a design-only model produces a complete, deterministic brief that a coding
agent could implement without further questions; both modes are golden-tested; the
existing delta output is unchanged; suite green; ruff clean.
```

## 6.4 Autonomous routines as activity diagrams

**Model: Opus** — new diagram semantics on top of the behavior canvas.

```
Autonomous routines are sequences of real commands, and the behavior canvas already has
the notation for them: start, end, decision, fork/join and join nodes.

1. Add a diagram type discriminator to `BehaviorDiagram` — `state_machine` (current
   behavior) or `activity` — defaulting to `state_machine` for existing diagrams. Bump
   `SCHEMA_VERSION` and migrate.
2. On an activity diagram, a state means "run this command": creating one offers the
   command list first and names itself after the chosen command, with the free-text name
   as the fallback.
3. Add "New Autonomous Routine" to the behavior model browser, seeded with a start node.
4. Compute and display the union of subsystem requirements along the routine, and flag
   two commands scheduled in parallel across a fork that require the same subsystem —
   that is the scheduler conflict that silently kills an auto routine, and the model can
   see it before the robot does. Add it as a Model Health rule.
5. Export activity diagrams as Mermaid `flowchart` blocks in step 6.2's section, and
   include the routine's command sequence in the AI brief.

Constraints: reuse `BehaviorScene`; do not fork a second canvas class. Keep pseudostate
rendering identical between the two diagram types.

Done when: an autonomous routine can be built from real commands, the parallel-requirement
conflict is detected with a unit test, both diagram types export correctly, and existing
state-machine diagrams are untouched; suite green; ruff clean.
```

---

# Phase 7 — Analysis

## 7.1 Interfaces and item flows

**Model: Opus** — new modelling semantics, and the point where the regex scanner strains.

```
MBSE value concentrates in interfaces. Model what subsystems exchange, so integration
mismatches surface at design review rather than at 2 a.m. on a practice field.

1. Add `Port` and `ItemFlow` to the domain: a port belongs to a subsystem and has a name,
   direction (provides / requires) and item type (free text with common suggestions —
   pose estimate, joystick input, setpoint, sensor reading, enable signal). An item flow
   connects a providing port to a requiring port. Bump `SCHEMA_VERSION` and migrate.
2. Ports render as small markers on the subsystem block edge; flows render as labeled
   edges with a distinct line style added to the legend data so the help panel picks them
   up automatically.
3. Add a flow view toggle alongside the hardware view states from step 3.2 — off by
   default. Ports and flows must not clutter a first look at the canvas.
4. Model Health rules: a requiring port with no incoming flow; a providing port nothing
   consumes (informational); a flow whose two ends disagree on item type.
5. Export an interface table: subsystem, port, direction, item type, connected element.

Constraints: do not attempt to infer ports from Java in this step. If it turns out the
regex scanner cannot support inference later, that is the moment to reconsider
Tree-sitter — note it, do not act on it here.

Done when: a Vision-provides-pose to Drivetrain-requires-pose flow can be modelled,
renders only when the toggle is on, exports as a table, and the mismatch rule has a unit
test; suite green; ruff clean.
```

## 7.2 Power, current and mass budgets

**Model: Sonnet** — arithmetic and presentation over fields that already exist.

```
Using the device fields from step 3.1, add budgets — the numbers a team argues about in
week four and measures at inspection.

1. Extend `services/allocation_service.py` with budget computation: total and
   per-subsystem mass, total and per-breaker-channel current, and headroom against
   configurable limits. Every limit is a constructor parameter with a documented default,
   because these rules change season to season.
2. Add a device type reference table mapping common types to typical stall and free
   current so a student gets a usable estimate before measuring anything. Mark every
   estimated value as estimated in the UI and the export — never present an estimate as
   measured.
3. Add a Budgets panel: mass by subsystem, current by channel, each as a bar against its
   limit with the over-limit portion visually distinct. Real numbers, tabular figures,
   units on every axis.
4. Export a budget section with the same figures and an explicit note of which values are
   estimates.

Constraints: no Qt in the service; do not invent precision the inputs do not have — round
sensibly and say what is estimated.

Done when: the sample robot produces a plausible budget, over-limit conditions are
visible on the panel and in Model Health, and unit tests cover the arithmetic including
empty and partial data; suite green; ruff clean.
```

## 7.3 Verification and competition readiness

**Model: Sonnet** — status tracking and a report, over existing entities.

```
Close the loop: how does anyone know the robot does what was designed?

1. Add verification to `Requirement`: `method` (inspect / demonstrate / test / analyse),
   `status` (not started / in progress / passed / failed), `evidence` free text, and a
   date. Bump `SCHEMA_VERSION` and migrate.
2. Add a bench-test status to Subsystem and Command with the same status vocabulary, so a
   team can track "the elevator has actually been run" separately from "the elevator was
   designed".
3. Add a Readiness report — the artifact a drive team wants the night before an event:
   requirements by verification status, unverified must-have requirements listed first,
   untested subsystems and commands, open Model Health findings, and unresolved
   allocation conflicts. Exportable as Markdown.
4. Show status as chips in the requirements tree and on canvas blocks, behind a view
   toggle so it does not clutter design work.

Constraints: status is authored, never inferred. Do not derive "passed" from anything
automatic — a person asserts it.

Done when: statuses round-trip, the readiness report renders deterministically and is
golden-tested, and the sample robot shows a realistic mix of statuses; suite green;
ruff clean.
```

## 7.4 Impact analysis

**Model: Sonnet** — a graph walk that half exists already inside a delete guard.

```
"What breaks if I change this?" is currently answered only as a refusal dialog inside
`delete_selected()`. Promote that graph walk into a first-class view.

1. Add `services/impact_service.py`: given any entity id, return everything that depends
   on it and everything it depends on, transitively, with the path for each — requirement
   satisfaction, command requirements, device ownership, typed relationships, item flows,
   behavior references, and triggers.
2. Add an Impact panel showing both directions as trees, with each row naming the link
   type that connects it. Click to select and reveal.
3. Reuse it for the cascade-delete dialog from step 1.2 so the two can never disagree
   about consequences.
4. Add a "Show impact" item to every canvas context menu.

Constraints: no Qt in the service; results must be deterministically ordered; handle
cycles without recursing forever.

Done when: selecting a subsystem shows its devices, requiring commands, satisfied
requirements and connected flows in one view; cycle handling has a unit test; the delete
dialog is driven by the same service; suite green; ruff clean.
```

---

# Phase 8 — Compounding value

## 8.1 Season library

**Model: Opus** — entity identity and merge semantics; easy to get subtly wrong.

```
Year two of using this tool should start faster than year one. Let a team import parts of
a previous season's model.

1. Add "Import from Model…" — choose an existing sidecar model, browse its subsystems,
   commands and requirements, select what to bring over, and import.
2. Identity is the hard part: imported entities get NEW UUIDs, and every internal
   reference among the imported set is remapped consistently — a subsystem's devices, its
   ports, and the requirements that satisfy it must all still point at each other
   afterwards, and at nothing in the source model.
3. Handle name collisions explicitly: offer rename, skip, or import-as-duplicate per
   element. Never silently merge two things because they share a name.
4. Cross-boundary references that cannot come along — an imported command requiring a
   subsystem the user did not select — are either pulled in as dependencies (offer this)
   or dropped with an explicit report. Never leave a dangling id; the project validator
   would reject it on save anyway.
5. Import is one undoable action.

Constraints: read the source model through `ProjectStore`; never mutate it. Write the
remapping as a pure, unit-testable function that takes entities and returns remapped
entities — the UI should be a thin wrapper over it.

Done when: importing a swerve drivetrain with devices and requirements produces a valid
project with no shared ids and no dangling references, proven by a unit test that
validates the resulting project; collisions are user-resolved; suite green; ruff clean.
```

## 8.2 Design decision records

**Model: Sonnet** — a small entity plus an inspector section and an export section.

```
Teams argue about elevator versus arm, then lose the reasoning. Capture it with the
design it shaped.

1. Add a `DesignDecision` entity: title, the question, options considered (each with pros
   and cons), the decision, rationale, date, and `affects: list[UUID]` linking to the
   elements it shaped. Bump `SCHEMA_VERSION` and migrate.
2. Show decisions in the inspector of any element they affect, and add a Decisions list
   view for the whole model.
3. Export a Decisions section in the Architecture Markdown, ordered by date, and cite
   relevant decisions in the AI change request so a coding agent does not re-litigate a
   settled choice.
4. Add a Model Health rule, informational only: a subsystem with no recorded decision and
   more than a threshold number of devices probably represents an undocumented choice.

Constraints: keep it lightweight. This is a record, not a workflow — no approvals, no
states, no assignees.

Done when: a decision can be recorded, linked to two subsystems, and appears in both
their inspectors and the export; suite green; ruff clean.
```

## 8.3 Verify the model against the real robot

**Model: Opus** — external integration, threading, and a deliberate crossing of an MVP non-goal.

```
Close design, code and reality into one loop. This step deliberately crosses the MVP
non-goal "no runtime telemetry" — it belongs last, and only because everything above it
is solid.

1. Add an optional NetworkTables client behind an importer-style interface, so the rest
   of the application never imports the networking library directly and the feature
   degrades cleanly when the dependency is absent.
2. Connect to a robot by team number or address. All I/O off the UI thread, following the
   `ui/scan_worker.py` pattern exactly — cancellable, progress-reporting, and never
   blocking the event loop.
3. Read what the standard WPILib tables expose: scheduled commands, registered subsystems,
   and any device telemetry published. Present it as a third layer beside design and
   scanned code — the same `FieldValue` layering idea, extended with observed fact.
4. Report drift: modelled subsystems the robot never reports, commands that never run,
   and devices absent from the bus. This is a live wiring check as much as a model check.
5. Read-only, always. This tool never writes to a robot.

Constraints: the whole feature must be skippable — if the library is not installed or no
robot is reachable, everything else works unchanged and the UI says so plainly. Tests use
a fake client; no test may require a robot or a network.

Done when: connecting to a simulated robot populates the observed layer, drift is
reported against the sample model, the feature is fully optional, and no test needs a
network; suite green; ruff clean.
```

---

## Summary

| Step | Work | Model |
| --- | --- | --- |
| 0 | Standing context (`CLAUDE.md`) | Sonnet |
| 1.1 | Single-form entity dialogs | Sonnet |
| 1.2 | Edit/delete for devices, triggers, relationships | **Opus** |
| 1.3 | Tooltips and contextual help | Sonnet |
| 1.4 | Zoom to fit, label collisions, truncation | Sonnet |
| 2.1 | Decompose `main_window.py` | **Opus** |
| 3.1 | Extended device fields and migration | **Opus** |
| 3.2 | Device blocks on a collapsible tier | **Opus** |
| 3.3 | Hardware table view | Sonnet |
| 3.4 | Allocation conflict detection | Sonnet |
| 4.1 | Sample robot and Java fixture | Sonnet |
| 4.2 | Start screen and empty states | Sonnet |
| 4.3 | Templates and automatic addressing | Sonnet |
| 4.4 | Model Health panel | **Opus** |
| 4.5 | Guided tour | Sonnet |
| 4.6 | Layered auto-layout | **Opus** |
| 5.1 | Requirement entity and traces | **Opus** |
| 5.2 | Requirements workspace | Sonnet |
| 5.3 | Coverage matrix and export | Sonnet |
| 6.1 | Wire behavior to structure | Sonnet |
| 6.2 | Behavior in the Markdown export | Sonnet |
| 6.3 | Design-only AI change request | **Opus** |
| 6.4 | Autonomous activity diagrams | **Opus** |
| 7.1 | Interfaces and item flows | **Opus** |
| 7.2 | Power, current and mass budgets | Sonnet |
| 7.3 | Verification and readiness | Sonnet |
| 7.4 | Impact analysis | Sonnet |
| 8.1 | Season library import | **Opus** |
| 8.2 | Design decision records | Sonnet |
| 8.3 | Verify against the real robot | **Opus** |

Twelve Opus steps, eighteen Sonnet. If you want the shortest path to a tool a new student
can use, stop after **4.4** — that is Phase 1 through the Model Health panel, and it
covers every dead end in the audit plus the sample robot to learn from.
