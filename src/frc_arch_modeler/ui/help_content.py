"""Help panel notation text, generated from the same data the canvases draw from.

``RELATIONSHIP_HELP`` and ``BEHAVIOR_STATE_KIND_HELP`` are keyed by the exact
dictionaries ``ArchitectureScene`` and ``BehaviorScene`` use to choose markers and
shapes -- ``RELATIONSHIP_MARKERS`` and ``BEHAVIOR_STATE_KINDS``. ``build_help_sections``
checks coverage against those before rendering anything, so a new relationship type or
behavior state kind cannot go undocumented the way the Join pseudostate once did.
"""

from __future__ import annotations

from typing import NamedTuple

from frc_arch_modeler.domain.model import BEHAVIOR_STATE_KINDS
from frc_arch_modeler.ui.architecture_scene import (
    MATCHED_GREEN,
    MODIFIED_AMBER,
    RELATIONSHIP_MARKERS,
    UNRESOLVED_MAGENTA,
)
from frc_arch_modeler.ui.theme import OFF_WHITE, VOLTAGE_BLUE, VOLTAGE_YELLOW

RELATIONSHIP_HELP: dict[str, str] = {
    "calls": (
        "<b>Calls</b> — dotted line, hollow arrowhead. One command or subsystem "
        "invokes another directly."
    ),
    "triggers": (
        "<b>Triggers</b> — dotted line, filled arrowhead. A trigger condition starts "
        "a command."
    ),
    "contains": (
        "<b>Contains</b> — dotted line, hollow diamond at the owner end. A subsystem "
        "groups a device or sub-part."
    ),
    "owns_device": (
        "<b>Owns Device</b> — dotted line, filled diamond at the owner end. A "
        "subsystem owns and controls a physical device."
    ),
}

BEHAVIOR_STATE_KIND_HELP: dict[str, str] = {
    "state": (
        "<b>State</b> — rounded rectangle. A named robot operating mode, such as "
        "Autonomous or Teleop."
    ),
    "start": (
        f"<span style='color:{VOLTAGE_YELLOW}'>&#9679;</span> <b>Start</b> — filled "
        "circle. Marks which state the robot enters first."
    ),
    "end": (
        f"<span style='color:{VOLTAGE_YELLOW}'>&#9678;</span> <b>End</b> — ringed "
        "circle. Marks that this branch of behavior has finished."
    ),
    "decision": (
        "&#9670; <b>Decision</b> — diamond. Branches to a different state depending "
        "on a guard condition."
    ),
    "synchronization": (
        f"<span style='color:{OFF_WHITE}'>&#9644;</span> <b>Split/Merge Bar</b> — "
        "solid bar. Forks one flow into concurrent states, or merges concurrent flows "
        "back into one."
    ),
    "join": (
        "<b>Join</b> — small circle. Lets multiple incoming transitions converge onto "
        "one outgoing line, with no branching logic."
    ),
}


class HelpSection(NamedTuple):
    """One help panel entry, tagged with which diagram tab it explains."""

    title: str
    html: str
    context: str  # "structure" or "behavior"


def build_help_sections() -> list[HelpSection]:
    """Return help sections covering every notation the canvas draws.

    Each section is tagged "structure" or "behavior" so the help panel can show only
    what's relevant to whichever diagram tab is active. Raises ``ValueError`` if a
    relationship type or behavior state kind exists with no matching help entry,
    instead of silently shipping an incomplete legend.
    """
    missing_relationships = sorted(set(RELATIONSHIP_MARKERS) - set(RELATIONSHIP_HELP))
    if missing_relationships:
        raise ValueError(
            f"No help text for relationship type(s): {', '.join(missing_relationships)}"
        )
    missing_states = sorted(set(BEHAVIOR_STATE_KINDS) - set(BEHAVIOR_STATE_KIND_HELP))
    if missing_states:
        raise ValueError(
            f"No help text for behavior state kind(s): {', '.join(missing_states)}"
        )

    relationship_rows = "<br>".join(RELATIONSHIP_HELP[key] for key in RELATIONSHIP_MARKERS)
    state_rows = "<br>".join(BEHAVIOR_STATE_KIND_HELP[kind] for kind in BEHAVIOR_STATE_KINDS)

    return [
        HelpSection(
            "Block accent",
            f"<span style='color:{VOLTAGE_YELLOW}'>&#9632;</span> Command &nbsp; "
            f"<span style='color:{VOLTAGE_BLUE}'>&#9632;</span> Subsystem",
            "structure",
        ),
        HelpSection(
            "Comparison status",
            "Status is always shown as a badge plus a border style, never color "
            "alone.<br>"
            f"<span style='color:{MATCHED_GREEN}'>&#10003; MATCHED</span> — solid "
            "border, design and code agree<br>"
            f"<span style='color:{MODIFIED_AMBER}'>&Delta; MODIFIED</span> — "
            "dash-dot border, code has diverged from design<br>"
            f"<span style='color:{VOLTAGE_YELLOW}'>+ DESIGN ONLY</span> — dashed "
            "border, not implemented yet<br>"
            f"<span style='color:{VOLTAGE_BLUE}'>&#8595; CODE ONLY</span> — dotted "
            "border, found in code but not designed<br>"
            f"<span style='color:{UNRESOLVED_MAGENTA}'>? UNRESOLVED / AMBIGUOUS</span> "
            "— needs manual binding<br>"
            "<span style='color:#FF5C5C'>! SCAN ERROR</span> — the scanner couldn't "
            "parse this symbol<br>"
            "IMPORTED — dotted border, scanned code with no design match yet",
            "structure",
        ),
        HelpSection(
            "Relationship lines",
            "Dashed — design requirement. "
            f"<span style='color:{VOLTAGE_BLUE}'>Dashed, blue</span> — imported "
            "requirement, hover for evidence.<br>"
            f"{relationship_rows}<br>"
            "Bright solid — connected to the current selection.",
            "structure",
        ),
        HelpSection(
            "Drawing a relationship",
            "Drag from a block's small yellow handle onto another block, then pick a "
            "relationship type.",
            "structure",
        ),
        HelpSection(
            "Behavior tab",
            "A separate state diagram for robot modes such as Disabled, Autonomous, "
            "Teleop and Test. States and transitions are authored the same way as the "
            "structure canvas: drag from a state's handle onto another state to add a "
            "transition. Click a transition to select it and reveal its two yellow "
            "endpoint handles — drag one onto a different state to reconnect it. "
            "Right-click a transition for a Delete Transition option.",
            "behavior",
        ),
        HelpSection(
            "Behavior palette",
            "The toolbar above the Behavior canvas adds SysML-style nodes to the "
            f"diagram:<br>{state_rows}<br>"
            "Transition labels may be left blank for start/end/split-merge edges.",
            "behavior",
        ),
    ]
