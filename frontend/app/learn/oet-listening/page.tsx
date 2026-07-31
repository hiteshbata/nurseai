import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { SummaryBox } from '@/components/learn/SummaryBox'
import { Callout } from '@/components/learn/Callout'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET Listening Guide for Nurses: How to Pass the OET Listening Sub-Test'
const DESCRIPTION =
  'A complete OET Listening guide for nurses: the 3-part format explained, what each part is really testing, a phase-by-phase exam strategy for single-listen audio, a full worked example, and 18 mistakes that quietly cost marks.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/learn/oet-listening' },
}

const toc = [
  { id: 'what-is-oet-listening', label: 'What is OET Listening?' },
  { id: 'format', label: 'The format' },
  { id: 'how-listening-is-scored', label: 'What each part is really testing' },
  { id: 'step-by-step-strategy', label: 'A phase-by-phase exam strategy' },
  { id: 'worked-example', label: 'A full worked example' },
  { id: 'common-mistakes', label: '18 mistakes that quietly cost marks' },
  { id: 'tutor-tips', label: 'Tips from experienced OET tutors' },
  { id: 'faq', label: 'Frequently asked questions' },
  { id: 'related-guides', label: 'Related guides' },
]

const faqs = [
  {
    q: 'How long is the OET Listening sub-test?',
    a: 'Around 45 minutes in total. Unlike Reading, the pace isn’t set by a clock you manage yourself — it’s set by the recordings, which run continuously through all three parts with built-in pauses for you to read upcoming questions and write your answers.',
  },
  {
    q: 'Can I replay a recording during the real test?',
    a: 'No. Every recording plays once, in real time, with no rewind and no way to pause it yourself. This is the single biggest difference from Reading and Writing, where you control the pace entirely — in Listening, the audio controls you.',
  },
  {
    q: 'Is spelling important in the Part A note-completion answers?',
    a: 'Yes. You’re writing down what you hear as a short word or phrase, and an examiner needs to recognise it as the correct term — a badly misspelled drug name or number can cost you the mark even if you clearly understood the audio correctly.',
  },
  {
    q: 'Is OET Listening scored on criteria, like Writing and Speaking?',
    a: 'No. Like Reading, Listening is scored purely on correct answers out of the total, converted into a band out of 6 and then into a letter grade and 0–500 score. There’s no qualitative judgement of your understanding, only whether each answer is right.',
  },
  {
    q: 'What accents will I hear in OET Listening?',
    a: 'A mix of native English accents — commonly British, Australian, New Zealand, and North American — reflecting the range of colleagues and patients you’d realistically work with. If your listening practice has only ever used one accent, this is often the first surprise on test day.',
  },
  {
    q: 'How many questions are there in total?',
    a: 'Around 42: about 24 in Part A (two consultation extracts, 12 note-completion blanks each), 6 in Part B (one 3-option question per short extract, across 6 extracts), and about 12 in Part C (two longer extracts, roughly 6 questions each). Exact counts can vary slightly between test versions.',
  },
  {
    q: 'What’s a good OET Listening score for nurses?',
    a: 'Most regulators, including the UK NMC, ask for at least Grade B (350/500) in Listening, the same threshold as the other three sub-tests. Requirements differ by regulator and do change, so check your target country’s current number with our score calculator or the official OET site.',
  },
  {
    q: 'Can I fail Listening while passing Reading, Writing, and Speaking?',
    a: 'Yes. Each of the four sub-tests is graded independently and most regulators set a minimum grade for all of them. Listening is easy to under-rate in preparation because it feels passive compared to Writing or Speaking — in practice it demands constant, active note-taking.',
  },
  {
    q: 'Can I pause the recording to catch up if I fall behind?',
    a: 'No — in the real test, the audio runs continuously and doesn’t wait for you. If you miss part of an answer, the right move is to leave it and refocus on the next question rather than dwelling on what you missed, since the recording won’t give you a second chance at that section.',
  },
  {
    q: 'Is OET@Home Listening different from the paper-based test?',
    a: 'The structure, timing, and single-listen rule are the same; only the delivery changes (audio played through your computer for OET@Home, through speakers or headphones in a test centre for the in-person test). Always confirm current delivery details on the official OET website, since these are set by OET, not by us.',
  },
  {
    q: 'How can I practise single-listen discipline without official OET materials?',
    a: 'The habit that matters most — never rewinding, ever, even when you’re unsure — is one you can build with any audio, but it’s far more realistic with actual healthcare-context recordings and a genuine note-completion template. That combination, with instant part-by-part feedback, is what SpeakOET’s Listening practice is built to give you.',
  },
  {
    q: 'Does note-taking speed matter more than vocabulary?',
    a: 'For Part A specifically, yes — you usually understand the words being said; the challenge is writing the answer down accurately while the speaker has already moved on to the next sentence. Building a personal shorthand for common clinical terms matters as much as vocabulary range.',
  },
]

export default function OetListeningPillarPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd
        path="/learn/oet-listening"
        title={TITLE}
        description={DESCRIPTION}
        datePublished="2026-07-27"
      />

      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">
        OET Listening Guide for Nurses
      </h1>
      <p className="text-gray-500 text-lg mb-2">
        Everything a nurse needs to pass OET Listening: the 3-part format, what each part is
        really testing, a phase-by-phase strategy for audio that only plays once, a full worked
        example, and the mistakes that quietly cost marks.
      </p>
      <ArticleMeta date="2026-07-27" />

      <p className="text-gray-600 leading-relaxed mb-6">
        If you&rsquo;ve sat OET Listening before and felt like you were still writing your last
        answer when the next question had already started &mdash; that&rsquo;s not a sign you
        misunderstood the audio. It&rsquo;s a sign the exam&rsquo;s real skill isn&rsquo;t
        comprehension at all, it&rsquo;s keeping pace with a recording that never waits for you.
        Every other sub-test lets you set your own speed. Listening doesn&rsquo;t, and that single
        difference is what this guide is built around.
      </p>

      <SummaryBox
        rows={[
          { label: 'Time', value: '~45 minutes, paced by the audio, not a clock you control' },
          { label: 'Marks', value: 'Scored 0–6 band, converts to Grade A–E, 0–500 scale' },
          { label: 'Parts', value: '3 parts (A, B, C), ~42 questions total' },
          { label: 'Difficulty', value: 'High — single listen, no replay, no pause' },
          { label: 'Passing grade', value: 'Usually Grade B / 350 — confirm with your regulator' },
          { label: 'Who this is for', value: 'Nurses who fall behind mid-answer or find single-listen formats stressful' },
        ]}
      />

      <TableOfContents items={toc} />

      {/* ---------------------------------------------------------- */}
      <h2 id="what-is-oet-listening" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What is OET Listening?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Listening tests whether you can follow spoken healthcare English in real time and
        pull out the specific information you need &mdash; the same skill as taking notes during
        a handover while the outgoing nurse is already three sentences ahead of what you&rsquo;re
        writing, or catching the one instruction in a ward briefing that actually applies to your
        patient. It isn&rsquo;t testing whether you can eventually understand a recording; it&rsquo;s
        testing whether you can capture what matters the first and only time you hear it.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        That&rsquo;s the detail that separates Listening from every other sub-test: Reading lets
        you re-read a sentence three times if you need to, Writing lets you draft and redraft,
        Speaking at least lets you take a breath before you answer. Listening gives you one pass.
        Once a recording moves on, so does the test &mdash; there&rsquo;s no rewind button, in
        practice or on the day.
      </p>
      <Callout variant="tip" title="Why this catches out confident listeners">
        Understanding every word of a recording and successfully writing down the right answer
        under time pressure are different skills. Plenty of nurses who&rsquo;d have no trouble
        following the same conversation in person still lose marks because their pen is a beat
        behind the speaker.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        It also differs from general English listening tests in what you&rsquo;re actually
        listening to. Where IELTS Listening might give you a university lecture or a conversation
        about booking a campsite, OET gives you a patient consultation, a ward handover, or a
        healthcare conference talk &mdash; content shaped exactly like what you already hear on
        shift. The Part A note-completion template, in particular, is built to feel like the kind
        of structured form you&rsquo;d fill in while taking a patient history, not an abstract
        exam format.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="format" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        The format
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Listening has three parts, played back to back, each testing a different way of listening
        &mdash; and each recording plays exactly once.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Part</th>
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Recordings</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">Questions</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">A</td>
              <td className="py-2 pr-4">2 consultation extracts (health professional and patient)</td>
              <td className="py-2">~24 — note-completion blanks, 12 per extract</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">B</td>
              <td className="py-2 pr-4">6 short, independent workplace extracts</td>
              <td className="py-2">6 — one 3-option question per extract</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">C</td>
              <td className="py-2 pr-4">2 longer extracts (interview or presentation)</td>
              <td className="py-2">~12 — 3-option questions, ~6 per extract</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout variant="warning" title="One listen, no exceptions">
        Every recording plays exactly once, and you can&rsquo;t pause or rewind it yourself in the
        real test. If you miss a word or a number, the only useful move is to write your best
        guess and stay focused on what&rsquo;s coming next &mdash; not to dwell on what you missed.
      </Callout>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part A in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Two recordings of a health professional talking with a patient (or a carer), each
        accompanied by a printed notes template with 12 numbered blanks. You listen and complete
        the notes as a health professional would while taking a history &mdash; a word, a number,
        or a short phrase per blank, taken directly from what&rsquo;s said.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part B in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Six short, unrelated extracts &mdash; a voicemail, a handover snippet, a briefing to
        staff. Each one is followed by exactly one three-option (A/B/C) question, usually about
        the speaker&rsquo;s main point, purpose, or what the listener needs to do.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part C in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Two longer recordings &mdash; typically an interview with, or presentation by, a
        healthcare professional on a topic relevant to practice. Each is followed by around six
        three-option questions testing detailed understanding, opinion, and attitude, not just
        surface facts.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        The two formats reward slightly different listening. An interview has two speakers, so
        the interviewer&rsquo;s questions often preview what the answer is about to cover &mdash;
        listen to the question asked, not just the response. A presentation is one speaker
        talking continuously, so signposting language (&ldquo;firstly,&rdquo; &ldquo;however,&rdquo;
        &ldquo;the key point here is&rdquo;) is your main clue to where the structure &mdash; and
        the answers &mdash; are heading next.
      </p>

      <LearnCTA
        heading="Practise the part where marks actually slip away"
        description="Real single-listen audio with a genuine note-completion template — see exactly which part and which skill you're losing marks on."
        href="/practice/listening"
        label="Try OET Listening Practice"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="how-listening-is-scored" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What each part is really testing
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        As with Reading, there are no named judgement criteria here &mdash; your score is
        correct answers out of the total. But each part is built to test a different listening
        skill, and knowing which one changes how you should listen.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">1. Part A — real-time note-taking</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        The template tells you the shape of the answer before the audio even starts &mdash; a
        blank after &ldquo;dose:&rdquo; wants a number, a blank after &ldquo;referred to:&rdquo;
        wants a place or service. Reading that shape in advance is most of the battle.
      </p>
      <Callout variant="bad" title="Writing full sentences">
        &ldquo;The patient said that she has been taking one thousand milligrams once a
        day&rdquo; &mdash; by the time this is written, the speaker has moved on and the next
        blank is already unanswered.
      </Callout>
      <Callout variant="good" title="Writing only the answer">
        &ldquo;1000mg, once daily&rdquo; &mdash; captures exactly what&rsquo;s needed, fast enough
        to stay with the recording.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> before each Part A
        recording starts, read every blank on the template and predict what type of answer each
        one wants &mdash; a number, a name, a duration, a reason. You&rsquo;re listening to
        confirm a prediction, not starting from zero.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">2. Part A — catching self-corrections</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Real speech doesn&rsquo;t come out perfectly formed. Speakers correct themselves mid-sentence
        &mdash; and the correction, not the first thing said, is usually the answer.
      </p>
      <Callout variant="bad" title="Writing down the first figure heard">
        Patient: &ldquo;It&rsquo;s five hundred milligrams &mdash; no wait, sorry, my doctor
        increased it recently, so it&rsquo;s a thousand now.&rdquo; Writing &ldquo;500mg&rdquo;
        because that&rsquo;s what was said first.
      </Callout>
      <Callout variant="good" title="Listening past the correction">
        Recognising &ldquo;no wait&rdquo; and &ldquo;actually&rdquo; as signals that the true
        answer is what follows, and writing &ldquo;1000mg&rdquo;.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> treat phrases like
        &ldquo;sorry,&rdquo; &ldquo;actually,&rdquo; &ldquo;no wait,&rdquo; and &ldquo;I mean&rdquo;
        as a flag to overwrite whatever you just wrote, not as background noise.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">3. Part B — purpose from a single hearing</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        With one question per extract and no replay, Part B rewards a quick, confident read of
        what the speaker wants the listener to do &mdash; not a search for a hidden detail.
      </p>
      <Callout variant="bad" title="Second-guessing after the audio ends">
        Hearing a clear instruction, then changing your answer afterwards because one of the
        three options &ldquo;sounds more complicated,&rdquo; without new information to justify it.
      </Callout>
      <Callout variant="good" title="Committing to your first accurate read">
        Answering based on what was actually said the moment the recording ends, then moving
        straight to reading the next extract&rsquo;s question.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> read the Part B
        question before each extract plays, so you know exactly what you&rsquo;re listening for
        the moment it starts.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">4. Part C — attitude, opinion, and emphasis</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Longer interviews and presentations test whether you can hear not just facts but how a
        speaker feels about them &mdash; hesitation, emphasis, and phrases like &ldquo;the real
        issue is&hellip;&rdquo; often carry the answer more than the surrounding factual detail.
      </p>
      <Callout variant="bad" title="Answering only from the facts stated">
        Picking an option that repeats a fact from the recording, without noticing the speaker&rsquo;s
        tone made clear they disagreed with it.
      </Callout>
      <Callout variant="good" title="Listening for stance, not just content">
        Noticing when a speaker&rsquo;s pace slows, or they say &ldquo;although&rdquo; or
        &ldquo;to be honest,&rdquo; as a cue that their real opinion is coming next.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> when a Part C
        question asks for an opinion or attitude rather than a fact, listen specifically for
        hedging and contrast words rather than trying to recall every detail equally.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">5. How your answers become a grade</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Exactly like Reading, your raw score is correct answers out of total questions, converted
        into a band out of 6, then into a letter grade and 0&ndash;500 score on the same scale
        used across all four sub-tests. See our{' '}
        <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
          full breakdown of how band scores work
        </Link>{' '}
        for how that conversion applies across Listening, Reading, Writing, and Speaking.
      </p>
      <Callout variant="tip" title="There is no penalty for a wrong guess">
        A blank costs you the same as a wrong answer &mdash; nothing gained either way &mdash; so
        if you’re unsure between two options as a recording ends, guess rather than leave it empty.
      </Callout>

      <LearnCTA
        heading="Build real single-listen discipline"
        description="Practice mode gives you one play, a real note-completion template, and instant part-by-part feedback — the same conditions as the real test."
        href="/practice/listening"
        label="Practise Listening Free"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="step-by-step-strategy" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A phase-by-phase exam strategy
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        You can&rsquo;t manage a clock you don&rsquo;t control, so the strategy here is about what
        to do in each phase of the recording, not which minute to be on.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Phase</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What to do</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Before Part A starts</td>
              <td className="py-2">Read every blank on the notes template and predict the answer type for each one — number, name, duration, reason.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">During each Part A extract</td>
              <td className="py-2">Write short-hand only. If you miss a blank, leave it and stay with the audio — chasing it backwards costs you the next one too.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Pause between parts</td>
              <td className="py-2">Use the short gap to read the upcoming part&rsquo;s questions, not to review what you just wrote.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">During Part B</td>
              <td className="py-2">Read the question before each extract plays. Commit to your answer the moment it ends and move straight to the next question.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">During Part C</td>
              <td className="py-2">Skim all of that extract&rsquo;s questions first so you know what&rsquo;s coming, then listen for stance and emphasis as much as facts.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">End of test</td>
              <td className="py-2">Use any remaining time to fill in blanks you skipped with your best guess, and check your handwriting is legible where it matters.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout variant="warning" title="If you completely miss an answer">
        Write your best guess based on the answer type you predicted (a plausible number, a
        plausible name) and move on immediately. Losing one mark hurts far less than losing the
        next three because you were still thinking about it.
      </Callout>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Decision tree: fell behind mid-recording?</h3>
      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="mb-2"><span className="font-semibold text-[#0F2356]">Did you catch the general topic of what was just said, even if you missed the exact detail?</span></p>
        <p className="mb-2 pl-4">Yes → write your best guess for that blank using the answer type you predicted, then refocus fully on the next line.</p>
        <p className="pl-4">No → leave that blank empty for now and refocus fully on the next line — don&rsquo;t spend any more attention on what&rsquo;s already gone. Come back to it only if time remains at the very end.</p>
      </div>

      {/* ---------------------------------------------------------- */}
      <h2 id="worked-example" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A full worked example
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Here&rsquo;s a short, invented Part A-style extract with a notes template, and the
        real-time thinking a strong candidate does while it plays &mdash; not just the finished
        answers.
      </p>

      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Notes template (extract)</p>
        <p className="mb-1">Reason for visit: routine (1) ______ review</p>
        <p className="mb-1">Current dose: (2) ______ mg, once daily</p>
        <p className="mb-1">Reason for missed doses: (3) ______</p>
        <p>Referred to: (4) ______ clinic</p>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white shadow-sm p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Transcript</p>
        <p className="mb-2"><span className="font-semibold">Nurse:</span> So Mr. Ahmed, you&rsquo;re here today for your routine medication review, is that right?</p>
        <p className="mb-2"><span className="font-semibold">Patient:</span> Yes, that&rsquo;s right.</p>
        <p className="mb-2"><span className="font-semibold">Nurse:</span> And how much metformin are you taking at the moment?</p>
        <p className="mb-2"><span className="font-semibold">Patient:</span> I think it&rsquo;s five hundred &mdash; no wait, sorry, my doctor increased it recently, so it&rsquo;s a thousand milligrams now, once a day.</p>
        <p className="mb-2"><span className="font-semibold">Nurse:</span> Okay, one thousand milligrams once daily. And have you been managing to take it every day?</p>
        <p className="mb-2"><span className="font-semibold">Patient:</span> Mostly, yeah, but I missed a few doses last month &mdash; mainly because I ran out and couldn&rsquo;t get to the pharmacy in time.</p>
        <p><span className="font-semibold">Nurse:</span> I see. Okay, and I&rsquo;ll be referring you to the diabetes education clinic for some further support.</p>
      </div>

      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Before the audio starts</span>, the
        template already tells you the answer types: (1) needs a noun (what kind of review), (2)
        needs a number, (3) needs a reason, (4) needs a place or service name.
      </p>
      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Blank (2) is the trap.</span> The patient
        says &ldquo;five hundred&rdquo; first, then corrects to &ldquo;a thousand.&rdquo; A
        candidate writing as they hear, without recognising &ldquo;no wait&rdquo; as a
        self-correction signal, answers &ldquo;500mg&rdquo; &mdash; confidently, and wrongly.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">Answers:</span> (1) medication, (2) 1000mg
        (or &ldquo;1000&rdquo;), (3) ran out / couldn&rsquo;t get to the pharmacy, (4) diabetes
        education. Notice that none of these require full sentences &mdash; just the exact
        information the template asked for, written fast enough to be ready for the next line.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="common-mistakes" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        18 mistakes that quietly cost marks
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        None of these mean you didn&rsquo;t understand the recording &mdash; they mean the
        recording didn&rsquo;t wait for you to catch up.
      </p>
      <ol className="list-decimal pl-5 space-y-3 text-gray-600 mb-4">
        <li><span className="font-semibold text-[#0F2356]">Writing full sentences in Part A.</span> By the time it&rsquo;s written, the speaker has already moved past the next answer.</li>
        <li><span className="font-semibold text-[#0F2356]">Not reading the notes template before the audio starts.</span> You lose the free hint about what type of answer each blank wants.</li>
        <li><span className="font-semibold text-[#0F2356]">Missing a self-correction.</span> Writing the first figure a speaker gives instead of the corrected one that follows &ldquo;actually&rdquo; or &ldquo;no wait.&rdquo;</li>
        <li><span className="font-semibold text-[#0F2356]">Dwelling on a missed blank.</span> Trying to mentally replay what you just missed instead of staying with the live audio costs you the next answer too.</li>
        <li><span className="font-semibold text-[#0F2356]">Practising only with replay enabled.</span> Builds a habit that doesn&rsquo;t exist in the real, single-listen test.</li>
        <li><span className="font-semibold text-[#0F2356]">Confusing similar-sounding numbers.</span> Fifteen and fifty, thirteen and thirty, are common under time pressure.</li>
        <li><span className="font-semibold text-[#0F2356]">Second-guessing a Part B answer after the audio ends.</span> Changing a correct instinctive answer with no new information to justify it.</li>
        <li><span className="font-semibold text-[#0F2356]">Not reading the Part B question before its extract plays.</span> You end up listening for nothing in particular, then scrambling once the question appears.</li>
        <li><span className="font-semibold text-[#0F2356]">Losing concentration mid-way through a long Part C recording.</span> A momentary lapse in a two-minute extract can cost several questions at once.</li>
        <li><span className="font-semibold text-[#0F2356]">Answering Part C only from stated facts.</span> Missing questions that ask for the speaker&rsquo;s opinion or attitude, which is often signalled by tone rather than content.</li>
        <li><span className="font-semibold text-[#0F2356]">Freezing on an unfamiliar accent.</span> Losing several seconds of processing time adjusting, instead of continuing to listen while adapting.</li>
        <li><span className="font-semibold text-[#0F2356]">Guessing at spelling for an unfamiliar term.</span> A drug or condition name spelled unrecognisably can lose the mark even with the right general idea.</li>
        <li><span className="font-semibold text-[#0F2356]">Leaving a blank empty instead of guessing.</span> A blank scores zero for certain; a plausible guess based on the predicted answer type has real odds.</li>
        <li><span className="font-semibold text-[#0F2356]">Ignoring the pause between parts.</span> That short gap is your only chance to preview the next part&rsquo;s questions before the audio starts again.</li>
        <li><span className="font-semibold text-[#0F2356]">Writing illegibly under pressure.</span> An answer the examiner can&rsquo;t read is treated the same as a wrong one.</li>
        <li><span className="font-semibold text-[#0F2356]">Practising with only clear, scripted audio.</span> Real recordings include hesitation, filler words, and natural speech patterns that scripted practice audio doesn&rsquo;t prepare you for.</li>
        <li><span className="font-semibold text-[#0F2356]">Treating Listening as a low-priority sub-test.</span> Because it feels passive, it&rsquo;s often the least practised — and the one where preparation habits (prediction, shorthand) matter most.</li>
        <li><span className="font-semibold text-[#0F2356]">Never reviewing mistakes by part.</span> Losing marks repeatedly in the same place (say, Part A numbers) without noticing the pattern across practice sessions.</li>
      </ol>

      {/* ---------------------------------------------------------- */}
      <h2 id="tutor-tips" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        Tips from experienced OET tutors
      </h2>
      <ul className="list-disc pl-5 space-y-3 text-gray-600 mb-4">
        <li>Build a personal shorthand for common clinical terms (mg, hx, w/, freq, dx) before you sit any full practice test — Part A doesn&rsquo;t give you time to invent it on the day.</li>
        <li>Never rewind during practice, even when you&rsquo;re sure you missed something. The habit you build in practice is the habit you&rsquo;ll have on test day.</li>
        <li>Deliberately practise with a range of accents — British, Australian, New Zealand, North American — rather than sticking to whichever one you find easiest to understand.</li>
        <li>When a speaker says &ldquo;actually,&rdquo; &ldquo;sorry,&rdquo; &ldquo;I mean,&rdquo; or &ldquo;no wait,&rdquo; treat it as an instruction to update your answer, not as filler to ignore.</li>
        <li>Read every part&rsquo;s questions before its audio starts, every single time — it&rsquo;s the single highest-leverage habit in this sub-test.</li>
        <li>If you miss an answer, guess based on the answer type you predicted rather than leaving it blank — a plausible number beats an empty space every time.</li>
        <li>Review your practice mistakes by part and by cause (missed a self-correction, confused numbers, lost concentration) — the pattern usually points to one fixable habit, not a vocabulary gap.</li>
        <li>Practise taking notes from spoken audio that has nothing to do with OET — a podcast, a news bulletin, a colleague talking quickly — as a general skill. The habit of writing key words while still listening transfers directly, and you don&rsquo;t need exam material to build it.</li>
      </ul>

      <p className="text-gray-600 leading-relaxed mb-8">
        Always check the exact current format, timing, and question types on the official OET
        website &mdash; these details are set and occasionally updated by OET, not by us.
      </p>

      <FaqSection faqs={faqs} />

      {/* ---------------------------------------------------------- */}
      <h2 id="related-guides" className="text-2xl font-bold text-[#0F2356] mt-12 mb-4">
        Related guides
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 mb-4 text-sm">
        <Link href="/learn/oet-reading" className="text-[#0F2356] font-semibold underline">
          OET Reading Guide for Nurses
        </Link>
        <Link href="/learn/oet-writing" className="text-[#0F2356] font-semibold underline">
          OET Writing Guide for Nurses
        </Link>
        <Link href="/oet/speaking" className="text-[#0F2356] font-semibold underline">
          OET Speaking: The Complete Guide
        </Link>
        <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline">
          What is OET Speaking?
        </Link>
        <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
          OET Band Scores Explained
        </Link>
        <Link href="/learn/oet-speaking-tips" className="text-[#0F2356] font-semibold underline">
          OET Speaking Tips for Nurses
        </Link>
        <Link href="/learn/oet-vs-ielts" className="text-[#0F2356] font-semibold underline">
          OET vs IELTS
        </Link>
        <Link href="/oet/uk" className="text-[#0F2356] font-semibold underline">
          OET Requirements for the UK (NMC)
        </Link>
        <Link href="/oet/australia" className="text-[#0F2356] font-semibold underline">
          OET Requirements for Australia
        </Link>
        <Link href="/oet/ireland" className="text-[#0F2356] font-semibold underline">
          OET Requirements for Ireland
        </Link>
        <Link href="/oet/new-zealand" className="text-[#0F2356] font-semibold underline">
          OET Requirements for New Zealand
        </Link>
        <Link href="/oet/canada" className="text-[#0F2356] font-semibold underline">
          OET Requirements for Canada
        </Link>
        <Link href="/tools/oet-score-calculator" className="text-[#0F2356] font-semibold underline">
          Free OET Score Calculator
        </Link>
        <Link href="/tools/ai-study-plan-generator" className="text-[#0F2356] font-semibold underline">
          Free AI Study Plan Generator
        </Link>
        <Link href="/practice/mock" className="text-[#0F2356] font-semibold underline">
          Full 4-Skill Mock Test
        </Link>
      </div>

      <LearnCTA
        heading="Ready for audio that only plays once?"
        description="Free single-listen practice with a real note-completion template and instant, part-by-part feedback."
        href="/practice/listening"
        label="Start Free Listening Practice"
      />
    </main>
  )
}
