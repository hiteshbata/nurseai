'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

interface Turn { role: string; content: string }
interface CandidateEvent { event: string; turn_index: number; evidence_text: string; source: string; target_concern: string | null }
interface PatientEvent { event: string; turn_index: number; evidence_text: string; source?: string; revealed?: boolean | null; target_concern?: string | null }
interface StateTransition { field: string; before: string; after: string; cause_event: string | null; turn_index: number }
interface ConcernHistoryEntry { status: string; turn_index: number; cause_event: string | null }
interface ReopenedEvent { turn_index: number; from_status: string; to_status: string; reason: string }
interface ConcernOutcome {
  concern: string
  final_status: string
  resolved: boolean
  history: ConcernHistoryEntry[]
  resolved_at_turns: number[]
  reopened_events: ReopenedEvent[]
}
interface HiddenInfoCandidateTurn { turn_index: number; evidence_text: string; verification_status: string }
interface HiddenInfoOutcome {
  item: string
  candidate_detected: boolean
  verification_status: string
  final_status: string
  turn_index: number | null
  evidence_text: string | null
  candidate_turns: HiddenInfoCandidateTurn[]
}
interface JargonEvidence { term: string; turn_index: number; evidence_text: string; patient_reaction: string | null; clarified_afterward: boolean }
interface InteractionMetrics {
  turn_counts: { nurse: number; patient: number; total: number }
  jargon_events: number; empathy_events: number
  concern_exploration_events: number; understanding_check_events: number; dismissive_events: number
}
interface Evidence {
  candidate_events: CandidateEvent[]
  patient_events: PatientEvent[]
  concern_outcomes: ConcernOutcome[]
  state_transitions: StateTransition[]
  jargon_evidence: JargonEvidence[]
  interaction_metrics: InteractionMetrics
  hidden_info_outcomes: HiddenInfoOutcome[]
}

// Step 11: reconciled view -- same underlying facts as Evidence above, grouped
// by (event, turn) across deterministic + semantic sources with a provenance
// tag ("deterministic_rule" | "semantic_model" | "hybrid"). Never removes or
// replaces the raw Evidence sections below; this is purely additive.
interface UnifiedCandidateEvent { event: string; turn_index: number; target_concern: string | null; provenance: string; evidence: { source: string; evidence_text: string }[] }
interface UnifiedConcernTimelineEntry { turn_index: number; status: string; provenance: string; source_event: string | null; evidence_text: string | null; reopened: boolean; reopened_from: string | null }
interface UnifiedConcernOutcome {
  concern: string; deterministic_final_status: string; unified_believed_status: string
  resolved: boolean; timeline: UnifiedConcernTimelineEntry[]
  resolved_at_turns: number[]; reopened_events: ReopenedEvent[]
}
interface UnifiedHiddenInfoOutcome {
  item: string; candidate_detected: boolean; verification_status: string
  final_status: string; provenance: string; reason: string; turn_index: number | null; evidence_text: string | null
  candidate_turns: HiddenInfoCandidateTurn[]
}
interface UnifiedEvidence {
  candidate_events: UnifiedCandidateEvent[]
  concern_outcomes: UnifiedConcernOutcome[]
  hidden_info_outcomes: UnifiedHiddenInfoOutcome[]
}

// Task 11/12: impossible evidence combinations caught by the backend's
// check_integrity() -- empty in the overwhelmingly common case.
interface IntegrityViolation { item: string; violation: string; detail: string }

interface EvidenceResponse {
  session: {
    id: number; pipeline: string; user_id: string | null; scenario_id: number | null
    created_at: string | null; duration_seconds: number | null; reconstruction_note: string | null
  }
  scenario: { id: number; title: string | null; setting: string | null; interlocutor_card: Record<string, any> | null } | null
  transcript: Turn[]
  evidence: Evidence
  unified: UnifiedEvidence
  integrity_violations: IntegrityViolation[]
}

const NA = <span className="text-gray-400 italic">Not available</span>

// Step 4: text label always carries the meaning, color is a secondary cue --
// never the only signal. Tone is derived from the actual backend status
// string, the label shown IS that string (just spaced out), never invented.
type Tone = 'ok' | 'warn' | 'error' | 'muted'
const TONE_CLASS: Record<Tone, string> = {
  ok: 'text-green-700 bg-green-50 border-green-200',
  warn: 'text-amber-700 bg-amber-50 border-amber-200',
  error: 'text-red-700 bg-red-50 border-red-200',
  muted: 'text-gray-500 bg-gray-50 border-gray-200',
}
function Badge({ text, tone }: { text: string; tone: Tone }) {
  return (
    <span className={`inline-block text-xs font-mono rounded border px-1.5 py-0.5 ${TONE_CLASS[tone]}`}>
      {text}
    </span>
  )
}

const PROVENANCE_TONE: Record<string, Tone> = {
  deterministic_rule: 'muted',
  semantic_model: 'warn',
  hybrid: 'ok',
}
const provenanceTone = (p: string): Tone => PROVENANCE_TONE[p] ?? 'muted'

const VERIFICATION_TONE: Record<string, Tone> = {
  not_called: 'muted',
  verified_revealed: 'warn',
  verified_not_revealed: 'ok',
  provider_failure: 'error',
  parse_failure: 'error',
  token_limit: 'error',
  malformed_response: 'error',
}
const verificationTone = (status: string): Tone => VERIFICATION_TONE[status] ?? 'muted'

function TurnLink({ turnIndex }: { turnIndex: number | null }) {
  if (turnIndex === null) return <>{NA}</>
  return (
    <a href={`#turn-${turnIndex}`} className="text-blue-600 hover:underline">
      Turn {turnIndex} &rarr; view transcript
    </a>
  )
}

export default function SpeakingEvidenceDetailPage() {
  const params = useParams<{ pipeline: string; id: string }>()
  const [data, setData] = useState<EvidenceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [showRaw, setShowRaw] = useState(false)

  const load = useCallback(() => {
    return api.get(`/admin/speaking-evidence/${params.pipeline}/${params.id}/evidence`)
      .then((res) => setData(res.data))
      .catch(() => setNotFound(true))
  }, [params.pipeline, params.id])

  useEffect(() => {
    setLoading(true)
    load().finally(() => setLoading(false))
  }, [load])

  if (loading) return <div className="p-6 text-sm text-gray-500">Loading...</div>
  if (notFound || !data) return <div className="p-6 text-sm text-red-600">Session not found.</div>

  const { session, scenario, transcript, evidence, unified, integrity_violations: integrityViolations } = data

  const byTurn = (turnIndex: number) => ({
    candidate: evidence.candidate_events.filter((e) => e.turn_index === turnIndex),
    patient: evidence.patient_events.filter((e) => e.turn_index === turnIndex),
    transitions: evidence.state_transitions.filter((t) => t.turn_index === turnIndex),
  })

  const unifiedFor = (turnIndex: number, event: string) =>
    unified.candidate_events.find((u) => u.turn_index === turnIndex && u.event === event)
  const unifiedConcern = (concern: string) => unified.concern_outcomes.find((u) => u.concern === concern)
  const unifiedHiddenInfo = (item: string) => unified.hidden_info_outcomes.find((u) => u.item === item)

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <Link href="/admin/speaking-evidence" className="text-sm text-blue-600 hover:underline">
          &larr; Back to sessions
        </Link>
        <h1 className="text-2xl font-bold mt-1">Speaking Evidence Inspector</h1>
      </div>

      {/* Task 11/12: integrity violations -- an internally impossible evidence
          combination, not just an uncertain one. Empty in the normal case. */}
      {integrityViolations.length > 0 && (
        <section className="bg-red-50 border border-red-200 rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-2 text-red-800">Integrity violations</h2>
          <ul className="space-y-1 text-sm text-red-800">
            {integrityViolations.map((v, i) => (
              <li key={i}>
                <span className="font-mono text-xs bg-red-100 rounded px-1.5 py-0.5 mr-2">{v.violation}</span>
                <span className="font-medium">{v.item}</span> — {v.detail}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* A. Session info */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Session</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-gray-500">Session ID</dt><dd>{session.id}</dd>
          <dt className="text-gray-500">Pipeline</dt><dd className="capitalize">{session.pipeline}</dd>
          <dt className="text-gray-500">User</dt><dd>{session.user_id || NA}</dd>
          <dt className="text-gray-500">Scenario</dt><dd>{scenario?.title || (session.scenario_id ?? NA)}</dd>
          <dt className="text-gray-500">Setting</dt><dd>{scenario?.setting || NA}</dd>
          <dt className="text-gray-500">Created</dt><dd>{session.created_at || NA}</dd>
          <dt className="text-gray-500">Duration</dt><dd>{session.duration_seconds != null ? `${session.duration_seconds}s` : NA}</dd>
        </dl>
        {session.reconstruction_note && (
          <p className="mt-3 text-xs bg-yellow-50 text-yellow-800 border border-yellow-200 rounded px-2 py-1">
            {session.reconstruction_note}
          </p>
        )}
        {!scenario && (
          <p className="mt-3 text-xs bg-yellow-50 text-yellow-800 border border-yellow-200 rounded px-2 py-1">
            Scenario record not found -- evidence was computed with an empty interlocutor card.
          </p>
        )}
      </section>

      {/* B + C + D. Transcript with inline candidate/patient events and state transitions */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Transcript & detected evidence</h2>
        {transcript.length === 0 ? (
          <p className="text-sm text-gray-500">No transcript available.</p>
        ) : (
          <ol className="space-y-3">
            {transcript.map((turn, idx) => {
              const { candidate, patient, transitions } = byTurn(idx)
              return (
                <li key={idx} id={`turn-${idx}`} className="border-b last:border-0 pb-3 scroll-mt-4">
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs text-gray-400 w-14 shrink-0">Turn {idx}</span>
                    <span className={`text-xs font-semibold uppercase ${turn.role === 'nurse' ? 'text-blue-600' : 'text-purple-600'}`}>
                      {turn.role === 'nurse' ? 'Candidate' : 'Patient'}
                    </span>
                  </div>
                  <p className="text-sm ml-16 mt-1">{turn.content}</p>

                  {(candidate.length > 0 || patient.length > 0 || transitions.length > 0) && (
                    <div className="ml-16 mt-2 space-y-1">
                      {candidate.map((e, i) => {
                        const u = unifiedFor(idx, e.event)
                        return (
                          <div key={i} className="text-xs text-green-700 bg-green-50 rounded px-2 py-1 inline-flex items-center gap-1 mr-2">
                            {e.event === 'jargon_used' ? '⚠' : '✓'} {e.event}
                            {e.target_concern ? ` → ${e.target_concern}` : ''}
                            {u && <Badge text={u.provenance} tone={provenanceTone(u.provenance)} />}
                          </div>
                        )
                      })}
                      {patient.map((e, i) => (
                        <div key={i} className="text-xs text-purple-700 bg-purple-50 rounded px-2 py-1 inline-block mr-2">
                          {e.event}: {e.evidence_text}
                        </div>
                      ))}
                      {transitions.map((t, i) => (
                        <div key={i} className="text-xs text-gray-600 bg-gray-50 rounded px-2 py-1 inline-block mr-2">
                          {t.field}: {t.before} &rarr; {t.after}
                        </div>
                      ))}
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        )}
      </section>

      {/* Step 1/2/6. Hidden information inspector */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-1">Hidden information</h2>
        <p className="text-xs text-gray-500 mb-3">
          candidate detection &rarr; semantic verification &rarr; final status. This is the Step 6 false-positive
          pattern made visible: a reviewer should be able to tell &ldquo;the verifier said no&rdquo; from
          &ldquo;the verifier was never called.&rdquo;
        </p>
        {evidence.hidden_info_outcomes.length === 0 ? (
          <p className="text-sm text-gray-500">No hidden-information items defined for this scenario.</p>
        ) : (
          <div className="space-y-4">
            {evidence.hidden_info_outcomes.map((h, i) => (
              <div key={i} className="border rounded p-3 text-sm">
                <div className="font-medium mb-2">{h.item}</div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge text={h.candidate_detected ? 'candidate detected: yes' : 'candidate detected: no'}
                    tone={h.candidate_detected ? 'warn' : 'muted'} />
                  <span className="text-gray-300">&rarr;</span>
                  <Badge text={`verification: ${h.verification_status}`} tone={verificationTone(h.verification_status)} />
                  <span className="text-gray-300">&rarr;</span>
                  <Badge text={`final: ${h.final_status}`} tone={h.final_status === 'revealed' ? 'warn' : 'ok'} />
                  {(() => {
                    const u = unifiedHiddenInfo(h.item)
                    return u ? (
                      <>
                        <Badge text={`provenance: ${u.provenance}`} tone={provenanceTone(u.provenance)} />
                        <Badge text={`reason: ${u.reason}`} tone="muted" />
                      </>
                    ) : null
                  })()}
                </div>
                <div className="mt-2 text-xs text-gray-500">
                  Final turn: <TurnLink turnIndex={h.turn_index} />
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  Evidence: {h.evidence_text ? <span className="italic">&ldquo;{h.evidence_text}&rdquo;</span> : NA}
                </div>

                {/* Step 12B: every candidate turn shown as its own row --
                    a false-positive early candidate must never be
                    collapsed together with the genuine later disclosure
                    that actually determined final_status. */}
                {h.candidate_turns.length > 0 && (
                  <div className="mt-3 border-t pt-2">
                    <div className="text-xs text-gray-400 mb-1">Candidate turns ({h.candidate_turns.length})</div>
                    <ul className="space-y-1">
                      {h.candidate_turns.map((ct, ci) => (
                        <li key={ci} className="flex items-center gap-2 text-xs">
                          <TurnLink turnIndex={ct.turn_index} />
                          <Badge text={ct.verification_status} tone={verificationTone(ct.verification_status)} />
                          {ct.turn_index === h.turn_index && h.final_status === 'revealed' && (
                            <span className="text-amber-700 font-medium">&larr; disclosure turn</span>
                          )}
                          <span className="text-gray-500 italic truncate">&ldquo;{ct.evidence_text}&rdquo;</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* E. Concern lifecycle, with reopening history (Step 3/7) */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Concern lifecycle</h2>
        {evidence.concern_outcomes.length === 0 ? (
          <p className="text-sm text-gray-500">No concerns defined for this scenario.</p>
        ) : (
          <div className="space-y-4">
            {evidence.concern_outcomes.map((c, i) => {
              const reopenedByTurn = new Map(c.reopened_events.map((r) => [r.turn_index, r]))
              const timeline = [...c.history].sort((a, b) => a.turn_index - b.turn_index)
              const u = unifiedConcern(c.concern)
              return (
                <div key={i} className="text-sm">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{c.concern}</span>
                    <Badge text={`current: ${c.final_status}`} tone={c.resolved ? 'ok' : 'muted'} />
                    {u && u.unified_believed_status !== c.final_status && (
                      <Badge text={`unified belief: ${u.unified_believed_status}`} tone="warn" />
                    )}
                    {c.reopened_events.length > 0 && <Badge text={`reopened ${c.reopened_events.length}x`} tone="warn" />}
                  </div>
                  {timeline.length === 0 ? (
                    <p className="mt-1 text-xs text-gray-400 italic">Not raised — no lifecycle events.</p>
                  ) : (
                    <ol className="mt-2 ml-1 space-y-1.5 border-l-2 border-gray-100 pl-3">
                      {timeline.map((h, j) => {
                        const reopen = reopenedByTurn.get(h.turn_index)
                        return (
                          <li key={j} className="text-xs">
                            <span className="text-gray-400">Turn {h.turn_index}</span>{' '}
                            {reopen ? (
                              <Badge text={`REOPENED (${reopen.from_status} → ${reopen.to_status})`} tone="warn" />
                            ) : (
                              <span className="font-medium text-gray-700 uppercase">{h.status}</span>
                            )}
                            {h.cause_event && <span className="text-gray-500"> — cause: {h.cause_event}</span>}
                            {reopen && (
                              <div className="mt-0.5 ml-1 text-gray-500 italic">&ldquo;{reopen.reason}&rdquo;</div>
                            )}
                          </li>
                        )
                      })}
                    </ol>
                  )}
                  {u && u.timeline.some((t) => t.provenance !== 'deterministic_rule') && (
                    <div className="mt-2 ml-1 pl-3 border-l-2 border-amber-100">
                      <p className="text-xs text-amber-700 font-medium mb-1">Unified timeline (deterministic + semantic)</p>
                      <ol className="space-y-1">
                        {u.timeline.map((t, j) => (
                          <li key={j} className="text-xs">
                            <span className="text-gray-400">Turn {t.turn_index}</span>{' '}
                            <span className="font-medium text-gray-700 uppercase">{t.status}</span>{' '}
                            <Badge text={t.provenance} tone={provenanceTone(t.provenance)} />
                            {t.evidence_text && <span className="text-gray-500 italic"> &ldquo;{t.evidence_text}&rdquo;</span>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* F. Jargon evidence */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Jargon evidence</h2>
        {evidence.jargon_evidence.length === 0 ? (
          <p className="text-sm text-gray-500">No jargon detected.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="py-1 pr-4">Term</th>
                <th className="py-1 pr-4">Turn</th>
                <th className="py-1 pr-4">Patient reaction</th>
                <th className="py-1">Clarified afterward</th>
              </tr>
            </thead>
            <tbody>
              {evidence.jargon_evidence.map((j, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-1 pr-4">{j.term}</td>
                  <td className="py-1 pr-4">{j.turn_index}</td>
                  <td className="py-1 pr-4">{j.patient_reaction || NA}</td>
                  <td className="py-1">{j.clarified_afterward ? 'true' : 'false'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Interaction metrics */}
      <section className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3">Interaction metrics</h2>
        <dl className="grid grid-cols-3 gap-2 text-sm">
          <dt className="text-gray-500">Candidate turns</dt><dd>{evidence.interaction_metrics.turn_counts.nurse}</dd>
          <dt className="text-gray-500 col-start-1">Patient turns</dt><dd>{evidence.interaction_metrics.turn_counts.patient}</dd>
          <dt className="text-gray-500">Empathy events</dt><dd>{evidence.interaction_metrics.empathy_events}</dd>
          <dt className="text-gray-500">Concern exploration</dt><dd>{evidence.interaction_metrics.concern_exploration_events}</dd>
          <dt className="text-gray-500">Understanding checks</dt><dd>{evidence.interaction_metrics.understanding_check_events}</dd>
          <dt className="text-gray-500">Dismissive events</dt><dd>{evidence.interaction_metrics.dismissive_events}</dd>
          <dt className="text-gray-500">Jargon events</dt><dd>{evidence.interaction_metrics.jargon_events}</dd>
        </dl>
      </section>

      {/* G. Raw evidence, debug */}
      <section className="bg-white rounded-lg shadow p-4">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-sm text-blue-600 hover:underline"
        >
          {showRaw ? 'Hide' : 'Show'} raw SpeakingEvidence (debug)
        </button>
        {showRaw && (
          <pre className="mt-3 text-xs bg-gray-50 rounded p-3 overflow-x-auto">
            {JSON.stringify(evidence, null, 2)}
          </pre>
        )}
      </section>
    </div>
  )
}
