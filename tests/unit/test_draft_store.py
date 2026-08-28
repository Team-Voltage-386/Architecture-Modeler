from frc_arch_modeler.domain.model import ArchitectureProject, Command, FieldValue
from frc_arch_modeler.persistence.draft_store import DraftStore


def test_draft_store_round_trips_and_can_be_discarded(tmp_path) -> None:
    project = ArchitectureProject(
        name="Competition Robot", commands=[Command(name=FieldValue(design="Score"))]
    )
    store = DraftStore(tmp_path)

    destination = store.save(project)

    assert destination == tmp_path / ".frc-architecture" / "draft.json"
    assert store.load() is not None
    assert store.load().to_dict() == project.to_dict()

    store.discard()

    assert store.load() is None
