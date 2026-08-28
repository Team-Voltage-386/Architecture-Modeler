from frc_arch_modeler.importers.java.parser import JavaSyntaxParser


def test_java_syntax_parser_reports_tolerant_error_locations() -> None:
    parser = JavaSyntaxParser()

    assert parser.error_lines("class Robot {}") == []
    assert parser.error_lines("class Robot { void run( {") == [1]
