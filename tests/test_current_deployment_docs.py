from __future__ import annotations

from pathlib import Path

import pytest


AUTHORITY_DOCS = (
    Path("CLAUDE.md"),
    Path("README.md"),
    Path("docs/CLOSED_LOOP_SPEC.md"),
    Path("docs/IMPLEMENTATION_PLAN.md"),
)


def test_claude_document_starts_with_ascii_project_heading() -> None:
    content = Path("CLAUDE.md").read_bytes()
    assert content.startswith(b"# LIGHT-BELT project instructions\n")


@pytest.mark.parametrize("path", AUTHORITY_DOCS)
def test_authority_docs_define_the_same_nine_node_wled_default(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "DDP" in text
    assert "strip_32" in text
    assert "strip_21" in text
    assert "output_id: 1" in text
    assert "NOT HARDWARE VERIFIED" in text


@pytest.mark.parametrize("path", AUTHORITY_DOCS)
def test_authority_docs_mark_legacy_protocols_as_nonproduction(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    assert "historical compatibility" in text or "compatibility" in text
    assert "udp v3" in text or "udp-v3" in text
    assert "not" in text and "production" in text
    assert "app" in text and "restart" in text
