"""Pure Markdown -> Sanity Portable Text converter (Module 1 Section 8).

Deliberately isolated -- no HTTP, no Supabase, no Sanity client, no env
vars, no draft/blog coupling. See docs/SECTION_8_MARKDOWN_CONVERTER.md-
style report in the implementation report for the full audit; the short
version:

Scope is bounded by what studio/schemaTypes/post.ts's `body` field (a bare
`{type: 'block'}` array member) and the frontend's un-customized
`<PortableText value={post.body} />` (frontend/app/blog/[slug]/page.tsx)
can actually store and render:

  block styles:  normal, h1-h6, blockquote
  lists:         bullet, number (with `level` for nesting)
  decorators:    strong, em          (code/underline/strike-through exist
                                       in the schema/renderer but have no
                                       Markdown source syntax in scope here)
  annotations:   link (href only, scheme allow-listed)

Images, tables, code blocks and raw HTML blocks are NOT in scope --
see UnsupportedImageError / UnsupportedTableError below and the "raw HTML"
handling note. No new dependency was installed for this (see report);
the supported subset above is narrow enough that a small stdlib-only
parser is the smallest correct option (ponytail rung 3 beats rung 5).
"""
import re
from typing import Optional

_ALLOWED_LINK_SCHEMES = {"http", "https", "mailto", "tel"}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")

# Applied left-to-right, non-overlapping (re.finditer). No nested marks:
# "**bold *italic* text**" keeps the inner "*...*" as literal text -- a
# documented limitation, not a crash risk.
_INLINE_RE = re.compile(
    r"(?P<link>\[(?P<linktext>[^\]\n]+)\]\((?P<linkurl>(?:\([^\s()]*\)|[^()\s])+)(?:\s+\"[^\"]*\")?\))"
    r"|(?P<bold>\*\*(?P<boldtext>(?:(?!\*\*).)+)\*\*)"
    r"|(?P<italic>\*(?P<italictext>(?:(?!\*).)+)\*)"
)


class MarkdownConversionError(Exception):
    """Base class for controlled (non-crash) conversion refusals."""


class UnsupportedImageError(MarkdownConversionError):
    """Markdown image syntax found. Converting it would require uploading
    a real Sanity image asset (out of scope here -- see report Section 8),
    so this raises instead of fabricating a fake asset reference."""


class UnsupportedTableError(MarkdownConversionError):
    """GFM table syntax found. The Sanity schema has no table block type,
    so this raises instead of silently flattening/losing structure."""


def _href_is_safe(url: str) -> bool:
    stripped = re.sub(r"[\x00-\x20]", "", url)
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", stripped)
    if not match:
        return True  # relative link (e.g. "/blog/x", "#anchor") -- schema allows this
    return match.group(1).lower() in _ALLOWED_LINK_SCHEMES


def _parse_inline(text: str, block_key: str) -> tuple[list[dict], list[dict]]:
    spans: list[dict] = []
    mark_defs: list[dict] = []
    pos = 0
    span_i = 0
    link_i = 0

    def emit_plain(chunk: str):
        nonlocal span_i
        if not chunk:
            return
        spans.append({"_type": "span", "_key": f"{block_key}-s{span_i}", "text": chunk, "marks": []})
        span_i += 1

    for m in _INLINE_RE.finditer(text):
        emit_plain(text[pos:m.start()])
        pos = m.end()
        if m.group("link"):
            link_text = m.group("linktext")
            url = m.group("linkurl")
            if _href_is_safe(url):
                mark_key = f"{block_key}-l{link_i}"
                link_i += 1
                mark_defs.append({"_type": "link", "_key": mark_key, "href": url})
                spans.append({"_type": "span", "_key": f"{block_key}-s{span_i}", "text": link_text, "marks": [mark_key]})
                span_i += 1
            else:
                emit_plain(link_text)  # unsafe scheme -> plain text, link dropped
        elif m.group("bold"):
            spans.append({"_type": "span", "_key": f"{block_key}-s{span_i}", "text": m.group("boldtext"), "marks": ["strong"]})
            span_i += 1
        elif m.group("italic"):
            spans.append({"_type": "span", "_key": f"{block_key}-s{span_i}", "text": m.group("italictext"), "marks": ["em"]})
            span_i += 1

    emit_plain(text[pos:])
    if not spans:
        spans.append({"_type": "span", "_key": f"{block_key}-s0", "text": "", "marks": []})
    return spans, mark_defs


def _text_block(text: str, block_key: str, style: str = "normal", list_item: Optional[str] = None, level: Optional[int] = None) -> dict:
    children, mark_defs = _parse_inline(text, block_key)
    block = {"_type": "block", "_key": block_key, "style": style, "children": children, "markDefs": mark_defs}
    if list_item:
        block["listItem"] = list_item
        block["level"] = level or 1
    return block


def markdown_to_portable_text(markdown: Optional[str]) -> list[dict]:
    """Convert Markdown source to a list of Sanity Portable Text blocks.

    Pure function: no I/O, deterministic (same input -> same output,
    including `_key`s, which are derived from block/span position, not
    randomness or timestamps). Raises UnsupportedImageError /
    UnsupportedTableError for constructs the current schema can't store
    rather than silently producing invalid or lossy documents.
    """
    if not markdown or not markdown.strip():
        return []

    if _IMAGE_RE.search(markdown):
        raise UnsupportedImageError("Markdown images are not supported by this converter; see Section 8 report.")

    lines = markdown.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if _TABLE_SEPARATOR_RE.match(line) and i > 0 and "|" in lines[i - 1]:
            raise UnsupportedTableError("Markdown tables are not supported by this converter; see Section 8 report.")

    blocks: list[dict] = []
    paragraph_lines: list[str] = []
    blockquote_lines: list[str] = []
    block_i = 0

    def flush_paragraph():
        nonlocal block_i
        if paragraph_lines:
            text = " ".join(paragraph_lines).strip()
            if text:
                blocks.append(_text_block(text, f"b{block_i}"))
                block_i += 1
            paragraph_lines.clear()

    def flush_blockquote():
        nonlocal block_i
        if blockquote_lines:
            text = " ".join(blockquote_lines).strip()
            if text:
                blocks.append(_text_block(text, f"b{block_i}", style="blockquote"))
                block_i += 1
            blockquote_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()

        if not line.strip():
            flush_paragraph()
            flush_blockquote()
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            flush_blockquote()
            level_hashes, heading_text = heading_match.groups()
            blocks.append(_text_block(heading_text.strip(), f"b{block_i}", style=f"h{len(level_hashes)}"))
            block_i += 1
            continue

        blockquote_match = _BLOCKQUOTE_RE.match(line)
        if blockquote_match:
            flush_paragraph()
            blockquote_lines.append(blockquote_match.group(1))
            continue

        list_match = _LIST_ITEM_RE.match(line)
        if list_match:
            flush_paragraph()
            flush_blockquote()
            indent, marker, item_text = list_match.groups()
            list_item = "bullet" if marker in ("-", "*") else "number"
            level = len(indent) // 2 + 1
            blocks.append(_text_block(item_text.strip(), f"b{block_i}", list_item=list_item, level=level))
            block_i += 1
            continue

        flush_blockquote()
        paragraph_lines.append(line.strip())

    flush_paragraph()
    flush_blockquote()
    return blocks
