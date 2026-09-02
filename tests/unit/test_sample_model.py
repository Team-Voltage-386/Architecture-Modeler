"""The shipped sample robot: a full worked example a new student can take apart."""

from pathlib import Path

from frc_arch_modeler.domain.model import ComparisonState
from frc_arch_modeler.importers.java.scanner import JavaProjectScanner
from frc_arch_modeler.persistence.project_store import ProjectStore
from frc_arch_modeler.services.allocation_service import (
    SEVERITY_ERROR,
    SEVERITY_INCOMPLETE,
    AllocationService,
)
from frc_arch_modeler.services.reconcile_service import ReconciliationService

SAMPLE_MODEL_ROOT = Path(__file__).parents[2] / "resources" / "sample_model"
SAMPLE_FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "java_sample"


def test_sample_model_loads_and_validates() -> None:
    project = ProjectStore(SAMPLE_MODEL_ROOT).load()

    assert project.name
    assert len(project.subsystems) == 5
    assert len(project.commands) == 8
    assert len(project.devices) == 22
    assert len(project.behavior_diagrams) == 2


def test_sample_model_has_no_hardware_allocation_conflicts() -> None:
    """"No conflicts" means no duplicate or orphaned addresses and none left blank.

    A real quad-swerve robot's per-motor breaker ratings realistically sum well past
    the 120 A default total-current budget check, which is an informational warning
    about the whole robot rather than a conflict between two specific devices, so it
    is deliberately excluded from this assertion.
    """
    project = ProjectStore(SAMPLE_MODEL_ROOT).load()

    findings = AllocationService().check(project)

    assert [finding for finding in findings if finding.severity == SEVERITY_ERROR] == []
    assert [finding for finding in findings if finding.severity == SEVERITY_INCOMPLETE] == []


def test_sample_model_reconciles_against_its_fixture_in_all_four_comparison_states() -> None:
    project = ProjectStore(SAMPLE_MODEL_ROOT).load()
    scan = JavaProjectScanner().scan(SAMPLE_FIXTURE_ROOT)

    result = ReconciliationService().reconcile(project, scan)

    states = set(result.statuses.values())
    assert ComparisonState.MATCHED in states
    assert ComparisonState.MODIFIED in states
    assert ComparisonState.DESIGN_ONLY in states
    assert result.code_only
