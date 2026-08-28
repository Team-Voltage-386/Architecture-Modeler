from pathlib import Path

from frc_arch_modeler.domain.model import SourceAnchor
from frc_arch_modeler.ui.source_viewer import SourceViewerDialog


def test_source_viewer_loads_anchor_file_at_the_requested_line(qtbot) -> None:
    root = Path(__file__).parents[1] / "fixtures" / "java_basic"
    anchor = SourceAnchor("src/main/java/frc/robot/Drive.java", "frc.robot.Drive", 5, 5)
    dialog = SourceViewerDialog(root, anchor)
    qtbot.addWidget(dialog)

    assert dialog.editor.isReadOnly()
    assert "public class Drive" in dialog.editor.toPlainText()
    assert dialog.editor.textCursor().blockNumber() == 4
