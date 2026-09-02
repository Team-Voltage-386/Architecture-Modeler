from frc_arch_modeler.domain.model import BEHAVIOR_STATE_KINDS
from frc_arch_modeler.ui.architecture_scene import RELATIONSHIP_MARKERS
from frc_arch_modeler.ui.help_content import (
    BEHAVIOR_STATE_KIND_HELP,
    RELATIONSHIP_HELP,
    build_help_sections,
)


def test_every_relationship_marker_has_help_text() -> None:
    assert set(RELATIONSHIP_HELP) == set(RELATIONSHIP_MARKERS)


def test_every_behavior_state_kind_has_help_text() -> None:
    assert set(BEHAVIOR_STATE_KIND_HELP) == set(BEHAVIOR_STATE_KINDS)


def test_build_help_sections_raises_when_a_relationship_type_is_undocumented(
    monkeypatch,
) -> None:
    monkeypatch.setitem(RELATIONSHIP_MARKERS, "escalates", ("arrow", False))
    try:
        try:
            build_help_sections()
        except ValueError as error:
            assert "escalates" in str(error)
        else:
            raise AssertionError("expected build_help_sections to reject an undocumented marker")
    finally:
        del RELATIONSHIP_MARKERS["escalates"]


def test_build_help_sections_covers_every_section_title() -> None:
    titles = [section.title for section in build_help_sections()]
    assert titles == [
        "Block accent",
        "Comparison status",
        "Relationship lines",
        "Drawing a relationship",
        "Behavior tab",
        "Behavior palette",
    ]


def test_build_help_sections_tags_structure_and_behavior_sections_correctly() -> None:
    contexts = {section.title: section.context for section in build_help_sections()}
    assert contexts["Block accent"] == "structure"
    assert contexts["Comparison status"] == "structure"
    assert contexts["Relationship lines"] == "structure"
    assert contexts["Drawing a relationship"] == "structure"
    assert contexts["Behavior tab"] == "behavior"
    assert contexts["Behavior palette"] == "behavior"
    assert {section.context for section in build_help_sections()} == {"structure", "behavior"}
