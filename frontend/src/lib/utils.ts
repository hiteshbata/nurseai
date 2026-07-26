import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// PDF-extracted reading questions keep their original paper numbering
// ("1. ", "14 ") baked into content -- strip it so the app's own running
// number (which may differ, e.g. continuous across a whole test) is the
// only one shown.
export function stripLeadingQuestionNumber(content: string): string {
  // Strips a leading "1." / "1)" / "1 " AND a parenthesized blank marker "(1)"
  // (OET Listening Part A questions arrive as "(1) back injury sustained…" while
  // the player already prints its own question number, which double-numbered them).
  return content.replace(/^\s*\(?\d+\)?[.)]?\s+/, '')
}

/** OET Reading Part A mixes three question styles in one passage: text-matching
 * (mcq, options are "Text A".."Text D"), word/phrase answer (short_answer,
 * plain question), and sentence completion (short_answer, has a blank).
 * Used to group + label them the way the real paper does. */
export type PartASubgroup = 'matching' | 'phrase' | 'completion'

export function partASubgroup(q: { type: string; options?: string[] }, content: string): PartASubgroup {
  if (q.type === 'mcq') return 'matching'
  return content.includes('___') ? 'completion' : 'phrase'
}

export const PART_A_SUBGROUP_LABEL: Record<PartASubgroup, string> = {
  matching: 'Decide which text (A, B, C or D) the information comes from.',
  phrase: 'Answer with a word or short phrase from the texts.',
  completion: 'Complete each sentence with a word or short phrase from the texts.',
}

/** One of Part A's four source texts, split out of the concatenated passage
 * body so each can render in its own labelled box like the real OET paper. */
export interface PartAText {
  label: string // "Text A"
  title: string // first line after the label, e.g. "Paracetamol: contraindications..."
  body: string
}

/** A header line marking the start of one Part A text. Tolerant of however the
 * extractor formatted it: "Text A", "Text A:", "TEXT A", "## Text A",
 * "**Text A**", "Text A -", etc. Captures the letter. */
const PART_A_HEADER = /^\s*#{0,6}\s*\*{0,2}\s*text\s+([A-D])\b[\s:*.\-]*$/i

/** Part A's body is the four source texts concatenated with per-text header lines.
 * Split it back into the individual texts so each renders in its own labelled box
 * like the real OET paper. Returns a single untitled block if no headers are found
 * (so nothing ever disappears). */
export function splitPartATexts(body: string): PartAText[] {
  const sections: { label: string; lines: string[] }[] = []
  for (const line of body.split('\n')) {
    const m = line.match(PART_A_HEADER)
    if (m) sections.push({ label: `Text ${m[1].toUpperCase()}`, lines: [] })
    else if (sections.length) sections[sections.length - 1].lines.push(line)
  }
  if (sections.length === 0) return [{ label: '', title: '', body }]
  return sections.map((s) => {
    const lines = [...s.lines]
    while (lines.length && !lines[0].trim()) lines.shift()
    // A text that opens straight into a table (pipe row + `|---|` separator) has no
    // title line — pulling one would steal the table header and break the render.
    const opensWithTable = lines[0]?.includes('|') && /^[\s:|-]*-[\s:|-]*$/.test(lines[1]?.trim() ?? '')
    if (opensWithTable) return { label: s.label, title: '', body: lines.join('\n').trim() }
    // Otherwise the first non-empty line is the text's title; strip markdown heading/bold marks.
    const title = (lines.shift() ?? '').replace(/^#{1,6}\s*/, '').replace(/\*\*/g, '').trim()
    return { label: s.label, title, body: lines.join('\n').trim() }
  })
}

/** Same split as splitPartATexts, but keeps the raw header line and untouched
 * content lines so the admin editor can show one textarea per text (A-D) and
 * rebuild the full body byte-for-byte around whichever section changed. */
export interface PartASection { label: string; header: string; lines: string[] }

export function splitPartASectionsRaw(body: string): PartASection[] {
  const sections: PartASection[] = []
  for (const line of body.split('\n')) {
    const m = line.match(PART_A_HEADER)
    if (m) sections.push({ label: m[1].toUpperCase(), header: line, lines: [] })
    else if (sections.length) sections[sections.length - 1].lines.push(line)
  }
  return sections
}

export function joinPartASections(sections: PartASection[]): string {
  return sections.flatMap((s) => [s.header, ...s.lines]).join('\n')
}

/** Split `body` around the first occurrence of `sentence` (whitespace-insensitive
 * match, since AI-quoted evidence often differs from the passage only in spacing/
 * newlines) so the caller can wrap the middle segment in a highlight. Returns
 * before/match/after — match is '' (and before = whole body) if not found. */
export function locateEvidence(body: string, sentence: string): { before: string; match: string; after: string } {
  const needle = (sentence || '').trim()
  if (!needle) return { before: body, match: '', after: '' }
  // Build a whitespace-tolerant regex from the escaped needle so "a  b\nc" matches "a b c".
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
  const m = body.match(new RegExp(escaped))
  if (!m || m.index === undefined) return { before: body, match: '', after: '' }
  return { before: body.slice(0, m.index), match: m[0], after: body.slice(m.index + m[0].length) }
}
