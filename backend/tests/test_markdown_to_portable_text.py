"""Unit tests for app/services/markdown_to_portable_text.py (Module 1
Section 8). Pure function -- no network, no Supabase, no Sanity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.markdown_to_portable_text import (
    UnsupportedImageError,
    UnsupportedTableError,
    markdown_to_portable_text,
)


def _texts(block):
    return [span["text"] for span in block["children"]]


def test_empty_content():
    assert markdown_to_portable_text(None) == []
    assert markdown_to_portable_text("") == []
    assert markdown_to_portable_text("   ") == []
    assert markdown_to_portable_text("\n\n") == []


def test_one_paragraph():
    blocks = markdown_to_portable_text("Hello world.")
    assert len(blocks) == 1
    assert blocks[0]["_type"] == "block"
    assert blocks[0]["style"] == "normal"
    assert _texts(blocks[0]) == ["Hello world."]


def test_multiple_paragraphs():
    blocks = markdown_to_portable_text("Hello world.\n\nSecond paragraph.")
    assert len(blocks) == 2
    assert [b["style"] for b in blocks] == ["normal", "normal"]
    assert _texts(blocks[0]) == ["Hello world."]
    assert _texts(blocks[1]) == ["Second paragraph."]


def test_h1():
    blocks = markdown_to_portable_text("# Heading 1")
    assert blocks[0]["style"] == "h1"
    assert _texts(blocks[0]) == ["Heading 1"]


def test_h2():
    blocks = markdown_to_portable_text("## Heading 2")
    assert blocks[0]["style"] == "h2"


def test_h3():
    blocks = markdown_to_portable_text("### Heading 3")
    assert blocks[0]["style"] == "h3"


def test_bold():
    blocks = markdown_to_portable_text("This is **bold** text.")
    marks = [span["marks"] for span in blocks[0]["children"]]
    assert ["strong"] in marks
    bold_span = next(s for s in blocks[0]["children"] if s["marks"] == ["strong"])
    assert bold_span["text"] == "bold"


def test_italic():
    blocks = markdown_to_portable_text("This is *italic* text.")
    italic_span = next(s for s in blocks[0]["children"] if s["marks"] == ["em"])
    assert italic_span["text"] == "italic"


def test_supported_link():
    blocks = markdown_to_portable_text("[SpeakOET](https://speakoet.com)")
    span = blocks[0]["children"][0]
    assert span["marks"] == [blocks[0]["markDefs"][0]["_key"]]
    assert blocks[0]["markDefs"][0]["href"] == "https://speakoet.com"
    assert blocks[0]["markDefs"][0]["_type"] == "link"


def test_unsafe_javascript_link_becomes_plain_text():
    blocks = markdown_to_portable_text("[Click me](javascript:alert(1))")
    assert blocks[0]["markDefs"] == []
    assert _texts(blocks[0]) == ["Click me"]


def test_unsafe_data_and_vbscript_links_rejected():
    for url in ("data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)"):
        blocks = markdown_to_portable_text(f"[x]({url})")
        assert blocks[0]["markDefs"] == []


def test_relative_link_allowed():
    blocks = markdown_to_portable_text("[Blog](/blog)")
    assert blocks[0]["markDefs"][0]["href"] == "/blog"


def test_unordered_list():
    blocks = markdown_to_portable_text("- One\n- Two")
    assert [b["listItem"] for b in blocks] == ["bullet", "bullet"]
    assert [b["level"] for b in blocks] == [1, 1]
    assert _texts(blocks[0]) == ["One"]
    assert _texts(blocks[1]) == ["Two"]


def test_ordered_list():
    blocks = markdown_to_portable_text("1. One\n2. Two")
    assert [b["listItem"] for b in blocks] == ["number", "number"]


def test_nested_list():
    blocks = markdown_to_portable_text("- One\n- Two\n  - Nested")
    assert [b["level"] for b in blocks] == [1, 1, 2]
    assert blocks[2]["listItem"] == "bullet"
    assert _texts(blocks[2]) == ["Nested"]


def test_blockquote():
    blocks = markdown_to_portable_text("> A wise quote.")
    assert blocks[0]["style"] == "blockquote"
    assert _texts(blocks[0]) == ["A wise quote."]


def test_raw_html_becomes_literal_text_not_executed():
    blocks = markdown_to_portable_text("<script>alert(1)</script>")
    assert len(blocks) == 1
    assert blocks[0]["style"] == "normal"
    assert _texts(blocks[0]) == ["<script>alert(1)</script>"]
    # No block type other than "block" is ever produced for this input --
    # nothing here is rendered as HTML by the frontend, only as span text.
    assert blocks[0]["_type"] == "block"


def test_malformed_markdown_does_not_crash():
    inputs = [
        "**unterminated bold",
        "[broken link(",
        "### ",
        "-",
        "> ",
        "***",
        "[text](",
    ]
    for md in inputs:
        blocks = markdown_to_portable_text(md)
        assert isinstance(blocks, list)


def test_deterministic_output():
    md = "# Title\n\nSome **bold** and *italic* text with a [link](https://speakoet.com).\n\n- One\n- Two"
    assert markdown_to_portable_text(md) == markdown_to_portable_text(md)


def test_unsupported_image_raises():
    try:
        markdown_to_portable_text("![alt text](https://example.com/x.png)")
        assert False, "expected UnsupportedImageError"
    except UnsupportedImageError:
        pass


def test_unsupported_table_raises():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    try:
        markdown_to_portable_text(md)
        assert False, "expected UnsupportedTableError"
    except UnsupportedTableError:
        pass


def test_realistic_oet_blog_example():
    md = """# How to Improve OET Speaking

Introduction paragraph.

## Before the role-play

- Prepare your opening
- Clarify the patient's concern
- Use appropriate empathy

## During the role-play

Use **clear** and *patient-friendly* language.

[Practice with SpeakOET](https://speakoet.com)
"""
    blocks = markdown_to_portable_text(md)
    styles = [b.get("style") for b in blocks]
    assert styles[0] == "h1"
    assert "h2" in styles
    list_blocks = [b for b in blocks if b.get("listItem") == "bullet"]
    assert len(list_blocks) == 3
    link_block = next(b for b in blocks if b["markDefs"])
    assert link_block["markDefs"][0]["href"] == "https://speakoet.com"
    # deterministic across repeated calls
    assert markdown_to_portable_text(md) == blocks
