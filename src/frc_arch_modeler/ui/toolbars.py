"""Construction of the main toolbar, its action groups, and the behavior palette.

These are pure builders: they create actions on the window and connect them to
handlers the window already exposes, so the window keeps owning every action
attribute the rest of the application (and its tests) reach for by name.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QLineEdit, QMenu, QToolBar, QToolButton

from frc_arch_modeler.domain.model import ComparisonState
from frc_arch_modeler.ui.behavior_scene import state_kind_icon

if TYPE_CHECKING:
    from frc_arch_modeler.ui.main_window import MainWindow


def build_toolbar(window: MainWindow) -> None:
    toolbar = QToolBar("Architecture actions", window)
    toolbar.setMovable(False)
    window.addToolBar(toolbar)
    window._toolbar = toolbar
    window.new_model_action = window.addAction("New Model", window._prompt_new_project)
    window.new_model_action.setShortcut(QKeySequence.StandardKey.New)
    set_action_help(
        window.new_model_action,
        "Start a brand-new, empty architecture model. Use this when beginning a "
        "design from scratch, before any robot code exists.",
    )
    window.open_model_action = window.addAction("Open Model", window._prompt_open_project)
    window.open_model_action.setShortcut(QKeySequence.StandardKey.Open)
    set_action_help(
        window.open_model_action,
        "Open a previously saved architecture model from disk. Use this to resume "
        "work on a model you already created.",
    )
    window.open_sample_model_action = window.addAction(
        "Open Sample Model", window._prompt_open_sample_model
    )
    set_action_help(
        window.open_sample_model_action,
        "Copy the built-in example robot — a full swerve drivetrain, intake, "
        "elevator, shooter and climber — into a folder you choose, then open it. "
        "Use this to explore the tool on a real model before building your own.",
    )
    window.save_model_action = window.addAction("Save Model", window._prompt_save_project)
    window.save_model_action.setShortcut(QKeySequence.StandardKey.Save)
    window.save_model_action.setEnabled(False)
    set_action_help(
        window.save_model_action,
        "Save the current architecture model to disk. Use this after making design "
        "changes you want to keep.",
    )
    window.connect_robot_action = window.addAction(
        "Connect Robot Project", window._prompt_connect_robot_project
    )
    set_action_help(
        window.connect_robot_action,
        "Point the tool at an FRC robot code project so it can scan the Java source "
        "for commands, subsystems and devices. Use this the first time you want to "
        "compare your design against real code.",
    )
    window.refresh_code_action = window.addAction(
        "Refresh Code", window._refresh_robot_project_async
    )
    window.refresh_code_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
    window.refresh_code_action.setEnabled(False)
    set_action_help(
        window.refresh_code_action,
        "Re-scan the connected robot project to pick up recent code changes without "
        "disturbing your design. Use this after editing code outside the tool.",
    )
    window.cancel_scan_action = window.addAction("Cancel Scan", window.cancel_scan)
    window.cancel_scan_action.setEnabled(False)
    set_action_help(
        window.cancel_scan_action,
        "Stop a code scan that is currently running. Use this if a scan is taking "
        "too long or you connected the wrong project.",
    )
    window.compare_action = window.addAction("Compare Changes", window.compare_changes)
    window.compare_action.setEnabled(False)
    set_action_help(
        window.compare_action,
        "Compare the current design against the most recent code scan and mark what "
        "matches, what changed, and what only exists on one side. Use this after "
        "connecting or refreshing code to see how design and implementation diverge.",
    )
    window.accept_matches_action = window.addAction("Accept Matches", window.accept_matches)
    window.accept_matches_action.setEnabled(False)
    set_action_help(
        window.accept_matches_action,
        "Accept the tool's suggested matches between design elements and scanned "
        "code symbols, marking them as confirmed. Use this after Compare Changes "
        "when the automatic matches already look correct.",
    )
    window.bind_selected_action = window.addAction("Bind Selected", window.bind_selected)
    window.bind_selected_action.setEnabled(False)
    set_action_help(
        window.bind_selected_action,
        "Tell the tool that this design element and this scanned code symbol are "
        "the same thing — use it when a rename made the automatic match ambiguous.",
    )
    window.export_change_request_action = window.addAction(
        "Export AI Change Request", window._prompt_export_change_request
    )
    window.export_change_request_action.setEnabled(False)
    set_action_help(
        window.export_change_request_action,
        "Export a Markdown brief describing the differences between design and "
        "code, written for an AI coding assistant to implement. Use this when you "
        "want an LLM to bring the code in line with the design.",
    )
    window.export_architecture_action = window.addAction(
        "Export Architecture", window._prompt_export_architecture
    )
    window.export_architecture_action.setShortcut(QKeySequence("Ctrl+E"))
    window.export_architecture_action.setEnabled(False)
    set_action_help(
        window.export_architecture_action,
        "Export the current architecture as a human-readable Markdown document. "
        "Use this to share or archive a snapshot of the design.",
    )
    window.new_command_action = window.addAction("New Command", window._prompt_new_command)
    window.new_command_action.setEnabled(False)
    set_action_help(
        window.new_command_action,
        "Add a new Command — a robot action such as driving a distance or running "
        "an intake — to the design. Use this to model a piece of robot behavior "
        "that doesn't exist yet.",
    )
    window.new_subsystem_action = window.addAction("New Subsystem", window._prompt_new_subsystem)
    window.new_subsystem_action.setEnabled(False)
    set_action_help(
        window.new_subsystem_action,
        "Add a new Subsystem — a group of hardware such as a drivetrain or arm — "
        "to the design. Use this to model a mechanical or electrical grouping of "
        "devices.",
    )
    window.new_subsystem_from_template_action = window.addAction(
        "New Subsystem from Template", window._prompt_new_subsystem_from_template
    )
    window.new_subsystem_from_template_action.setEnabled(False)
    set_action_help(
        window.new_subsystem_from_template_action,
        "Create a common subsystem — swerve drivetrain, intake, elevator, and more "
        "— with all its devices already named, typed, and addressed in one step. "
        "Use this instead of adding each device by hand.",
    )
    window.new_command_from_template_action = window.addAction(
        "New Command from Template", window._prompt_new_command_from_template
    )
    window.new_command_from_template_action.setEnabled(False)
    set_action_help(
        window.new_command_from_template_action,
        "Create a Command, set its subsystem requirement, and optionally add a "
        "trigger in one step. Use this instead of three separate actions.",
    )
    window.new_device_action = window.addAction("New Device", window._prompt_new_device)
    window.new_device_action.setEnabled(False)
    set_action_help(
        window.new_device_action,
        "Add a new Device, such as a motor or sensor, owned by a subsystem. Use "
        "this to model a specific piece of hardware.",
    )
    window.new_trigger_action = window.addAction("New Trigger", window._prompt_new_trigger)
    window.new_trigger_action.setEnabled(False)
    set_action_help(
        window.new_trigger_action,
        "Add a new Trigger — a condition, like a button press or sensor threshold, "
        "that starts a Command. Use this to model what causes a command to run.",
    )
    window.new_relationship_action = window.addAction(
        "New Relationship", window._prompt_new_relationship
    )
    window.new_relationship_action.setEnabled(False)
    set_action_help(
        window.new_relationship_action,
        "Draw a new relationship, such as calls or triggers, between two selected "
        "design elements. Use this to model how commands, subsystems and devices "
        "interact.",
    )
    window.show_command_forms_action = window.addAction("Show Command Forms")
    window.show_command_forms_action.setCheckable(True)
    window.show_command_forms_action.toggled.connect(window._toggle_command_forms)
    set_action_help(
        window.show_command_forms_action,
        "Toggle whether each Command's parameter list is shown expanded on the "
        "canvas. Use this to see or hide command configuration details inline.",
    )
    window.link_selected_action = window.addAction(
        "Link Selected (Requires)", window.link_selected_requirement
    )
    window.link_selected_action.setShortcut(QKeySequence("Ctrl+L"))
    window.link_selected_action.setEnabled(False)
    set_action_help(
        window.link_selected_action,
        "Mark the second selected element as required by the first, recording a "
        "design dependency. Use this to capture that one part of the robot depends "
        "on another being built first.",
    )
    window.delete_selected_action = window.addAction(
        "Delete Selected", window._confirm_delete_selected
    )
    window.delete_selected_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
    window.delete_selected_action.setEnabled(False)
    set_action_help(
        window.delete_selected_action,
        "Delete the currently selected design elements from the model. Use this to "
        "remove commands, subsystems, devices or relationships you no longer want "
        "— press Ctrl+Z to undo.",
    )
    window.search_field = QLineEdit(window)
    window.search_field.setObjectName("architectureSearch")
    window.search_field.setAccessibleName("Search architecture evidence")
    window.search_field.setPlaceholderText("Search architecture")
    window.search_field.setClearButtonEnabled(True)
    window.search_field.textChanged.connect(window.scene.filter_blocks)
    window.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, window)
    window.find_shortcut.activated.connect(window.search_field.setFocus)
    window._status_filter_actions = {}
    for state, label, help_text in (
        (
            ComparisonState.MATCHED,
            "Matched",
            "Show or hide blocks whose design matches the scanned code exactly. "
            "Turn this off to reduce clutter while focusing on what's changed.",
        ),
        (
            ComparisonState.MODIFIED,
            "Modified",
            "Show or hide blocks where the code has diverged from the design. Turn "
            "this off to hide elements that already agree.",
        ),
        (
            ComparisonState.DESIGN_ONLY,
            "Design Only",
            "Show or hide blocks that exist in the design but haven't been "
            "implemented in code yet. Use this to see what's still to be built.",
        ),
        (
            ComparisonState.CODE_ONLY,
            "Code Only",
            "Show or hide blocks found in the scanned code that aren't part of the "
            "design yet. Use this to spot undocumented code.",
        ),
        (
            ComparisonState.UNRESOLVED,
            "Unresolved",
            "Show or hide blocks the tool couldn't confidently match between design "
            "and code. Use this to focus on matches that may need manual binding.",
        ),
        (
            ComparisonState.AMBIGUOUS,
            "Ambiguous",
            "Show or hide blocks with more than one possible code match. Use this "
            "to focus on matches that need manual review.",
        ),
        (
            ComparisonState.SCAN_ERROR,
            "Scan Error",
            "Show or hide blocks the code scanner couldn't parse. Use this to find "
            "files that need attention before comparing.",
        ),
    ):
        action = window.addAction(label)
        action.setCheckable(True)
        action.setChecked(True)
        action.toggled.connect(window._apply_status_filters)
        set_action_help(action, help_text)
        window._status_filter_actions[state] = action
    toolbar.addSeparator()
    window.undo_action = window.undo_stack.createUndoAction(window, "Undo")
    window.redo_action = window.undo_stack.createRedoAction(window, "Redo")
    set_action_help(
        window.undo_action,
        "Undo the most recent design change. Use this to step back one edit at a "
        "time, including canvas moves.",
    )
    set_action_help(
        window.redo_action,
        "Redo the design change you just undid. Use this to step forward again "
        "after an undo.",
    )
    window.auto_layout_action = window.addAction("Auto Layout", window.auto_layout)
    set_action_help(
        window.auto_layout_action,
        "Automatically rearrange all blocks into a tidy grid. Use this to clean up "
        "the canvas after adding or importing many elements.",
    )
    window.zoom_to_fit_action = window.addAction("Zoom to Fit", window.zoom_to_fit)
    set_action_help(
        window.zoom_to_fit_action,
        "Zoom and pan the canvas so every block is visible at once. Use this to "
        "get your bearings after scrolling or zooming in.",
    )
    window.minimize_action = window.addAction("Minimize Selected", window.minimize_selected)
    set_action_help(
        window.minimize_action,
        "Collapse the selected blocks down to a compact title-only size. Use this "
        "to reduce visual clutter for blocks you don't need full detail on right "
        "now.",
    )
    window.device_view_action = window.addAction(
        "Devices: Grouped", window._cycle_device_view
    )
    set_action_help(
        window.device_view_action,
        "Cycle how hardware devices are drawn: Grouped shows each subsystem a "
        "device-count chip you can click to expand just that subsystem, Expanded "
        "shows every device block at once, and Hidden shows none. Use this to study "
        "wiring without crowding the canvas.",
    )
    window.restore_action = window.addAction("Restore Selected", window.restore_selected)
    set_action_help(
        window.restore_action,
        "Expand previously minimized blocks back to full size. Use this to see "
        "full details again.",
    )
    for action in (
        window.auto_layout_action,
        window.zoom_to_fit_action,
        window.minimize_action,
        window.restore_action,
        window.device_view_action,
    ):
        action.setEnabled(False)
    organize_toolbar(window, toolbar)


def set_action_help(action, text: str) -> None:  # type: ignore[no-untyped-def]
    """Give a toolbar action the same one-sentence explanation as both its tooltip
    and its status-bar text, written for someone new to FRC architecture modeling."""
    action.setToolTip(text)
    action.setStatusTip(text)


def organize_toolbar(window: MainWindow, toolbar: QToolBar) -> None:
    """Replace a wrapping action strip with compact, named action groups."""
    toolbar.clear()

    def add_group(label: str, actions: list) -> QMenu:  # type: ignore[no-untyped-def]
        button = QToolButton(toolbar)
        button.setText(label)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.addActions(actions)
        button.setMenu(menu)
        toolbar.addWidget(button)
        return menu

    model_menu = add_group(
        "Model",
        [
            window.new_model_action,
            window.open_model_action,
            window.open_sample_model_action,
            window.save_model_action,
        ],
    )
    model_menu.addSeparator()
    window.open_recent_model_action = model_menu.addAction(
        "Recent", window._open_recent_model
    )
    window._refresh_recent_model_action()
    add_group(
        "Code",
        [
            window.connect_robot_action,
            window.refresh_code_action,
            window.cancel_scan_action,
            window.compare_action,
            window.accept_matches_action,
            window.bind_selected_action,
            window.show_command_forms_action,
            window.export_architecture_action,
            window.export_change_request_action,
        ],
    )
    add_group(
        "New",
        [
            window.new_command_action,
            window.new_command_from_template_action,
            window.new_subsystem_action,
            window.new_subsystem_from_template_action,
            window.new_device_action,
            window.new_trigger_action,
            window.new_relationship_action,
            window.link_selected_action,
        ],
    )
    add_group("Filters", list(window._status_filter_actions.values()))
    add_group(
        "View",
        [
            window.auto_layout_action,
            window.zoom_to_fit_action,
            window.minimize_action,
            window.restore_action,
            window.device_view_action,
        ],
    )
    toolbar.addSeparator()
    icon_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "assets"
    window.undo_action.setIcon(QIcon(str(icon_root / "ios-undo-e88c9d.svg")))
    window.redo_action.setIcon(QIcon(str(icon_root / "ios-redo-b88e64.svg")))
    toolbar.addAction(window.undo_action)
    toolbar.addAction(window.redo_action)
    toolbar.addSeparator()
    toolbar.addWidget(window.search_field)
    toolbar.addSeparator()
    toolbar.addAction(window.toggle_health_action)
    toolbar.addAction(window.toggle_help_action)


def build_behavior_toolbar(window: MainWindow) -> None:
    """A palette of SysML-style node buttons scoped to the Behavior tab, Cameo-style."""
    toolbar = QToolBar("Behavior palette", window)
    toolbar.setMovable(False)
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    window.new_behavior_state_action = toolbar.addAction(
        "New State", window._prompt_new_behavior_state
    )
    set_action_help(
        window.new_behavior_state_action,
        "Add a new named state to the behavior diagram, representing a robot "
        "operating mode such as Autonomous or Teleop. Use this to model a mode the "
        "robot can be in.",
    )
    window.new_behavior_start_action = toolbar.addAction(
        "Start", lambda: window._add_behavior_pseudostate("start")
    )
    set_action_help(
        window.new_behavior_start_action,
        "Add a Start pseudostate — a filled circle marking where the behavior "
        "diagram begins. Use this to show which state the robot enters first.",
    )
    window.new_behavior_end_action = toolbar.addAction(
        "End", lambda: window._add_behavior_pseudostate("end")
    )
    set_action_help(
        window.new_behavior_end_action,
        "Add an End pseudostate — a ringed circle marking a terminal state. Use "
        "this to show that a behavior sequence has finished.",
    )
    window.new_behavior_decision_action = toolbar.addAction(
        "Decision", lambda: window._add_behavior_pseudostate("decision")
    )
    set_action_help(
        window.new_behavior_decision_action,
        "Add a Decision diamond that branches into different states depending on "
        "a guard condition. Use this to model an if/else choice in robot behavior.",
    )
    window.new_behavior_sync_action = toolbar.addAction(
        "Split/Merge Bar", lambda: window._add_behavior_pseudostate("synchronization")
    )
    set_action_help(
        window.new_behavior_sync_action,
        "Add a Split/Merge bar, used to fork one flow into several concurrent "
        "states or merge several concurrent flows back into one. Use this to model "
        "behaviors that happen at the same time.",
    )
    window.new_behavior_join_action = toolbar.addAction(
        "Join", lambda: window._add_behavior_pseudostate("join")
    )
    set_action_help(
        window.new_behavior_join_action,
        "Add a Join — an unlabeled circular point where multiple incoming "
        "transitions converge onto one outgoing line. Use this to bring separate "
        "flows back together without branching logic.",
    )
    window._behavior_creation_actions = [
        window.new_behavior_state_action,
        window.new_behavior_start_action,
        window.new_behavior_end_action,
        window.new_behavior_decision_action,
        window.new_behavior_sync_action,
        window.new_behavior_join_action,
    ]
    for action, kind in zip(
        window._behavior_creation_actions,
        ("state", "start", "end", "decision", "synchronization", "join"),
    ):
        action.setEnabled(False)
        action.setIcon(state_kind_icon(kind))
    toolbar.addSeparator()
    window.behavior_zoom_to_fit_action = toolbar.addAction(
        "Zoom to Fit", window.behavior_zoom_to_fit
    )
    set_action_help(
        window.behavior_zoom_to_fit_action,
        "Zoom and pan the behavior canvas so every state is visible at once. Use "
        "this to get your bearings after scrolling or zooming in.",
    )
    window.behavior_zoom_to_fit_action.setEnabled(False)
    window.behavior_toolbar = toolbar

