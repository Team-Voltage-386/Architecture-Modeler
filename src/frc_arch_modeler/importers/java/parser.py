"""Tree-sitter Java parsing with non-fatal syntax diagnostics."""

from __future__ import annotations

import tree_sitter_java
from tree_sitter import Language, Parser


class JavaSyntaxParser:
    """Parse Java source while retaining syntax errors for the caller to report."""

    def __init__(self) -> None:
        self._parser = Parser(Language(tree_sitter_java.language()))

    def parse(self, source: str):  # type: ignore[no-untyped-def]
        return self._parser.parse(source.encode("utf-8"))

    def error_lines(self, source: str) -> list[int]:
        """Return one-based lines containing Tree-sitter ERROR or missing nodes."""
        tree = self.parse(source)
        lines: set[int] = set()
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type == "ERROR" or node.is_missing:
                lines.add(node.start_point.row + 1)
            stack.extend(node.children)
        return sorted(lines)
