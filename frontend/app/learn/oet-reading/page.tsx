import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { SummaryBox } from '@/components/learn/SummaryBox'
import { Callout } from '@/components/learn/Callout'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET Reading Guide for Nurses: How to Pass the OET Reading Sub-Test'
const DESCRIPTION =
  'A complete OET Reading guide for nurses: the 3-part format explained, what each question type is really testing, a minute-by-minute exam strategy, a full worked example, and 18 mistakes that quietly cost marks.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/learn/oet-reading' },
}

const toc = [
  { id: 'what-is-oet-reading', label: 'What is OET Reading?' },
  { id: 'format', label: 'The format' },
  { id: 'how-reading-is-scored', label: 'What each part is really testing' },
  { id: 'step-by-step-strategy', label: 'A minute-by-minute exam strategy' },
  { id: 'worked-example', label: 'A full worked example' },
  { id: 'common-mistakes', label: '18 mistakes that quietly cost marks' },
  { id: 'tutor-tips', label: 'Tips from experienced OET tutors' },
  { id: 'faq', label: 'Frequently asked questions' },
  { id: 'related-guides', label: 'Related guides' },
]

const faqs = [
  {
    q: 'How long is the OET Reading sub-test?',
    a: '60 minutes in total, split into two timed blocks: 15 minutes for Part A, then 45 minutes shared between Parts B and C. Once the Part A block ends you cannot go back to it, so all your Part A answers need to be in before the 15 minutes are up.',
  },
  {
    q: 'Is OET Reading scored on criteria, like Writing and Speaking?',
    a: 'No. Writing and Speaking are judged qualitatively against named criteria; Reading (like Listening) is scored purely on how many questions you get right, converted into a band out of 6 and then into a grade. There is no partial credit for a "nearly right" answer and no reward for elegant reasoning the examiner never sees.',
  },
  {
    q: 'Can I use my own clinical knowledge to answer a question?',
    a: 'No, and this catches out experienced nurses more than beginners. Every answer has to be supported by the text in front of you, not by what you already know is normally true in practice. If a passage says something that sounds clinically unusual, the question is testing whether you read carefully, not whether you spot the "error".',
  },
  {
    q: "What's a good OET Reading score for nurses?",
    a: 'Most regulators, including the UK NMC, ask for at least Grade B (350/500) in Reading, the same threshold as the other three sub-tests. Requirements differ by regulator and do change, so check your target country’s current number with our score calculator or the official OET site.',
  },
  {
    q: 'Is spelling important in Part A short-answer questions?',
    a: "Yes for the word/phrase and sentence-completion questions — you're expected to copy the exact word or short phrase from the text, so a spelling change can mean the answer isn't recognised as correct. This is different from Writing, where minor spelling slips are judged by whether they cause the reader confusion.",
  },
  {
    q: 'How many questions are there in total?',
    a: 'Roughly 42: about 20 in Part A (across matching, sentence completion, and short-answer questions on 4 short texts), about 6 in Part B (one 3-option question per short workplace text), and about 16 in Part C (two longer texts, each with around 8 four-option questions). Exact counts can vary slightly between test versions.',
  },
  {
    q: 'Is OET Reading harder than IELTS Reading?',
    a: "They test different things rather than one being objectively harder. IELTS Reading uses general and academic texts on unfamiliar topics; OET Reading uses healthcare workplace documents and clinical texts, which usually favours nurses — but the strict, unforgiving time pressure in Parts A and C surprises almost everyone the first time. See our full OET vs IELTS comparison for the broader picture.",
  },
  {
    q: 'Can I fail Reading while passing Listening, Writing, and Speaking?',
    a: 'Yes. Each of the four sub-tests is graded independently and most regulators set a minimum grade for all of them. Reading is often assumed to be the "easy" sub-test because it’s multiple choice, which is exactly why candidates under-prepare for its time pressure and lose marks they didn’t expect to.',
  },
  {
    q: 'Do all healthcare professions get the same Reading test?',
    a: "Part A and Part B texts are the same for every profession, but Part C's two longer texts are healthcare-general rather than nursing-specific — you won't get a text written only for doctors or only for nurses, but the topics are drawn from healthcare more broadly.",
  },
  {
    q: 'Can I go back and change a Part A answer once Part B starts?',
    a: 'No. Part A is a strictly timed 15-minute block, and once it ends (or you choose to move on), you move into the shared 45-minute Part B/C block and cannot return. Treat the Part A clock as a hard stop, not a soft target.',
  },
  {
    q: 'How can I practise OET Reading realistically without a tutor?',
    a: "The two things that matter most — realistic healthcare texts and an accurate clock — are exactly what's hard to recreate with random articles and an untimed read. Practising full timed passages with instant, question-type-specific feedback is what actually builds exam-day pace; that's what SpeakOET's Reading practice is built for.",
  },
  {
    q: 'Is OET@Home Reading different from the paper-based test?',
    a: 'The structure, timing, and question types are the same; only the delivery changes (on-screen for OET@Home, paper booklet for the in-person test). Always confirm current delivery options and any format updates on the official OET website, since these are set by OET, not by us.',
  },
]

export default function OetReadingPillarPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd
        path="/learn/oet-reading"
        title={TITLE}
        description={DESCRIPTION}
        datePublished="2026-07-27"
      />

      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">
        OET Reading Guide for Nurses
      </h1>
      <p className="text-gray-500 text-lg mb-2">
        Everything a nurse needs to pass OET Reading: the 3-part format, what each question type
        is really testing, a minute-by-minute strategy, a full worked example, and the mistakes
        that quietly cost marks under time pressure.
      </p>
      <ArticleMeta date="2026-07-27" />

      <p className="text-gray-600 leading-relaxed mb-6">
        If you&rsquo;ve come out of OET Reading thinking &ldquo;I understood everything, I just
        didn&rsquo;t finish&rdquo; &mdash; you&rsquo;re not alone, and you&rsquo;re also not
        wrong about what went wrong. Reading is the sub-test most candidates under-prepare for,
        because it looks like the easy one: no speaking, no writing, just multiple choice. In
        practice it&rsquo;s a speed test disguised as a comprehension test, and the clock is
        usually the reason a strong reader walks out with a lower grade than expected. This
        guide is built around exactly that problem.
      </p>

      <SummaryBox
        rows={[
          { label: 'Time', value: '60 minutes (15 min Part A + 45 min Parts B & C)' },
          { label: 'Marks', value: 'Scored 0–6 band, converts to Grade A–E, 0–500 scale' },
          { label: 'Parts', value: '3 parts (A, B, C), ~42 questions total' },
          { label: 'Difficulty', value: 'High under time pressure — a speed & scanning test' },
          { label: 'Passing grade', value: 'Usually Grade B / 350 — confirm with your regulator' },
          { label: 'Who this is for', value: 'Nurses who run out of time, or "understood it but still lost marks"' },
        ]}
      />

      <TableOfContents items={toc} />

      {/* ---------------------------------------------------------- */}
      <h2 id="what-is-oet-reading" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What is OET Reading?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Reading tests whether you can find, understand, and use information from healthcare
        texts quickly &mdash; the same skill you use every shift when you scan a drug
        information leaflet for a contraindication, skim a hospital policy update for what
        actually changed, or read a discharge summary to find the one line that matters for your
        handover. It isn&rsquo;t testing whether you can read English in general; it&rsquo;s
        testing whether you can read healthcare English fast, under pressure, and pull out the
        right detail.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        The test is entirely multiple-choice and short-answer &mdash; there&rsquo;s nothing to
        write in your own words and nothing an examiner judges for style. That sounds easier than
        Writing or Speaking, and in one sense it is: there&rsquo;s no register or tone to get
        wrong. But every mark comes from correctly locating information inside a strict clock,
        which is a completely different skill from &ldquo;understanding&rdquo; a text if you had
        unlimited time.
      </p>
      <Callout variant="tip" title="Why strong readers still lose marks here">
        Reading well and reading fast enough are not the same skill. Plenty of nurses who read
        fluently in English still run out of time in Part C, because they read every sentence with
        equal care instead of hunting for the specific answer to the specific question in front of
        them.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        It also differs from a general English reading test in what the texts are actually about.
        Where IELTS Reading might give you an unfamiliar academic passage on astronomy or urban
        planning, OET gives you a drug insert, a discharge summary, an infection-control memo, or
        a clinical guideline extract &mdash; material your ward experience has already trained you
        to skim for the relevant line. That&rsquo;s a genuine advantage for nurses, provided your
        exam technique doesn&rsquo;t waste it on unnecessary re-reading.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="format" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        The format
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Reading has three parts, and they don&rsquo;t feel like variations on the same task
        &mdash; each one rewards a different reading skill, timed separately from the others.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Part</th>
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Time</th>
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Texts</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">Questions</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">A</td>
              <td className="py-2 pr-4">15 minutes</td>
              <td className="py-2 pr-4">4 short texts, one shared topic</td>
              <td className="py-2">~20 — matching, sentence completion, short answer</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">B</td>
              <td className="py-2 pr-4" rowSpan={2}>45 minutes (shared)</td>
              <td className="py-2 pr-4">6 short workplace texts</td>
              <td className="py-2">6 — one 3-option question per text</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">C</td>
              <td className="py-2 pr-4">2 longer healthcare texts</td>
              <td className="py-2">~16 — 4-option questions, ~8 per text</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout variant="warning" title="Part A has a hard stop">
        The 15 minutes for Part A is a separate clock. Once it ends, you move into the shared
        45-minute block for Parts B and C and cannot return to Part A &mdash; so every Part A
        answer needs to be committed before time runs out, not left to &ldquo;come back to
        later.&rdquo;
      </Callout>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part A in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Four short texts (labelled Text A–D) all on one healthcare topic &mdash; think four
        different extracts about the same medication, condition, or hospital procedure. Around 20
        questions are split across matching (which text says X), sentence completion (fill the gap
        using words from the text), and short-answer (write the exact word or short phrase the
        text uses). It&rsquo;s explicitly designed as an &ldquo;expeditious reading&rdquo; task
        &mdash; OET is testing speed of locating information, not slow, careful comprehension.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part B in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Six short, unrelated workplace texts &mdash; the kind of thing that actually lands in a
        ward pigeonhole or inbox: a memo, a policy extract, a set of guidelines, an incident
        report excerpt. Each one gets exactly one three-option (A/B/C) question, usually about the
        text&rsquo;s main purpose, what a reader should do, or what a specific instruction means.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Part C in detail</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Two longer, more academic or discursive healthcare texts, each followed by around eight
        four-option (A/B/C/D) questions. This is where most of your 45-minute B/C block should go
        &mdash; the questions test detailed comprehension, inference, the writer&rsquo;s opinion or
        purpose, and vocabulary in context, not just fact-location.
      </p>

      <LearnCTA
        heading="Feel the real time pressure"
        description="Practise full timed Reading passages and see your words-per-minute and accuracy broken down by part — not just a final score."
        href="/practice/reading"
        label="Try OET Reading Practice"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="how-reading-is-scored" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What each part is really testing
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Because Reading has no named criteria like Writing&rsquo;s Content or Genre & Style, it&rsquo;s
        easy to assume every question is testing the same thing: &ldquo;did you understand the
        text.&rdquo; In practice each part is built around a specific skill, and knowing which
        skill is being tested changes how you should read the question.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">1. Part A matching — scanning, not reading</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        &ldquo;Which text mentions the recommended dosage for renal impairment?&rdquo; is a
        scanning task: you&rsquo;re hunting for a keyword or concept across four texts, not
        absorbing each one in full.
      </p>
      <Callout variant="bad" title="Reading each text start to finish">
        Reading Text A, then B, then C, then D in full before answering wastes most of your 15
        minutes on content that isn&rsquo;t relevant to any question.
      </Callout>
      <Callout variant="good" title="Reading the question, then scanning">
        Read the question first, note the keyword or concept, then scan each text&rsquo;s
        headings and topic sentences for it before reading closely.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> practise reading
        the question stem before you even look at the four texts &mdash; decide what word or idea
        you&rsquo;re hunting for, then go find it, instead of building a full mental model of all
        four texts first.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">2. Part A completion & short answer — exact wording</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        These questions want the text&rsquo;s own word or short phrase, copied accurately &mdash;
        not a paraphrase, however correct in meaning.
      </p>
      <Callout variant="bad" title="Paraphrasing the answer">
        The text says &ldquo;administer with food&rdquo;; writing &ldquo;take after eating&rdquo;
        may be marked wrong even though it means the same thing, because it isn&rsquo;t the
        text&rsquo;s wording.
      </Callout>
      <Callout variant="good" title="Copying the exact phrase">
        Locate the relevant sentence, then lift the precise word or short phrase requested,
        checking spelling against the text rather than from memory.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> once you find the
        right sentence, copy directly rather than typing from memory &mdash; a confident
        misspelling is a more common cause of lost marks here than not finding the answer at all.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">3. Part B — purpose and instruction, not detail</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        With only one question per text, Part B is usually asking about the text&rsquo;s overall
        purpose, its intended reader, or what action it requires &mdash; not a buried detail.
      </p>
      <Callout variant="bad" title="Overthinking a simple purpose question">
        Searching for a hidden trick in a straightforward memo, and second-guessing an obviously
        correct option because it &ldquo;seems too easy.&rdquo;
      </Callout>
      <Callout variant="good" title="Trusting the plain reading">
        If the memo says staff must complete a form by Friday, and the question asks what staff
        are required to do, the literal answer is usually the correct one.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> read each Part B
        text once for its main point before looking at the question &mdash; you&rsquo;ll usually
        already know the answer before you&rsquo;ve read the three options.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">4. Part C — inference and distractor elimination</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Part C questions test whether you can infer a writer&rsquo;s opinion, understand a
        cause-and-effect relationship, or work out a word&rsquo;s meaning from context &mdash; and
        the wrong options are deliberately built from real words in the text, just recombined to
        change the meaning.
      </p>
      <Callout variant="bad" title="Picking the option with familiar words">
        Choosing an option because it repeats vocabulary from the passage, without checking
        whether it actually states what the passage says.
      </Callout>
      <Callout variant="good" title="Eliminating against the text, not against memory">
        Going back to the exact sentence a plausible-sounding option is based on, and checking
        whether the option changes its meaning (adds a cause, reverses a direction, overstates a
        claim).
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> treat every option
        as a claim to verify against a specific sentence, not a general impression of what the
        passage was about.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">5. How your answers become a grade</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Unlike Writing and Speaking, Reading has no partial credit for reasoning &mdash; your raw
        score is simply correct answers out of total questions, converted into a band out of 6,
        which then maps to a letter grade and a 0&ndash;500 score, the same scale used across all
        four sub-tests. See our{' '}
        <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
          full breakdown of how band scores work
        </Link>{' '}
        for how that conversion applies across Reading, Listening, Writing, and Speaking.
      </p>
      <Callout variant="tip" title="There is no penalty for a wrong guess">
        Because your score is simply correct answers out of total questions, an incorrect answer
        costs you nothing beyond not gaining the mark. That makes leaving a question blank the
        single worst option available to you — always fill in your best guess before time runs out.
      </Callout>

      <LearnCTA
        heading="Find your weak part, not just your final score"
        description="SpeakOET breaks your Reading results down by Part A, B and C — and by skill, like scanning, inference, and vocabulary in context."
        href="/practice/reading"
        label="Practise Reading Free"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="step-by-step-strategy" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A minute-by-minute exam strategy
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        &ldquo;Manage your time&rdquo; means nothing without numbers attached. Here&rsquo;s how to
        actually spend the 60 minutes.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Time</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What to do</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">0–1 min</td>
              <td className="py-2">Skim the Part A topic and headings of all four texts — don&rsquo;t read them yet, just get oriented.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">1–14 min</td>
              <td className="py-2">Work question by question: read the question, scan for the answer, commit it, move on. Don&rsquo;t leave any blank — a guess beats nothing.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">14–15 min</td>
              <td className="py-2">Final check that every Part A answer is filled in. The clock does not pause for you here.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">15–20 min</td>
              <td className="py-2">Move straight into Part B. Budget roughly 3 minutes per text including its question — six texts, about 18 minutes total.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">33–58 min</td>
              <td className="py-2">Part C: roughly 12–13 minutes per text. Read the whole text once before answering any of its ~8 questions, rather than hunting question by question in a long passage.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">58–60 min</td>
              <td className="py-2">Fill in any remaining guesses across B and C. An educated guess on a 3- or 4-option question has real odds — a blank has none.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout variant="warning" title="If a Part C question is taking too long">
        Mark your best guess and move on rather than re-reading the same paragraph a fourth time.
        One stuck question can cost you two or three answers elsewhere if it eats five minutes.
      </Callout>
      <Callout variant="warning" title="If you finish Part C early">
        Don&rsquo;t just stop. Go back to any question you flagged as uncertain and re-check it
        against the text one more time &mdash; not from memory, from the actual sentence.
      </Callout>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Decision tree: stuck on a question?</h3>
      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="mb-2"><span className="font-semibold text-[#0F2356]">Have you found the exact sentence the question is based on?</span></p>
        <p className="mb-2 pl-4">No → keep scanning for the keyword or concept in the question, don&rsquo;t start guessing between options yet.</p>
        <p className="mb-2 pl-4">Yes → does one option directly restate that sentence&rsquo;s meaning?</p>
        <p className="mb-2 pl-8">Yes → select it and move on immediately.</p>
        <p className="pl-8">No → eliminate any option that reverses, overstates, or invents a claim the sentence doesn&rsquo;t make; guess among what&rsquo;s left and move on within 90 seconds.</p>
      </div>

      {/* ---------------------------------------------------------- */}
      <h2 id="worked-example" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A full worked example
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Here&rsquo;s a short, invented Part C-style extract and question, with the elimination
        process a strong candidate actually uses &mdash; not just the correct answer.
      </p>

      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Extract</p>
        <p>
          Since the ward introduced a standardised sepsis-screening tool at admission, the time
          between a patient meeting screening criteria and the first dose of antibiotics has
          fallen by an average of 40 minutes. Nursing staff report that the tool is quick to use,
          though several noted that its usefulness depends entirely on being completed at the
          point of admission rather than retrospectively. Where screening was delayed until after
          the initial assessment was complete, the time-to-antibiotics improvement largely
          disappeared. The trust is now reviewing whether screening should be built into the
          admission checklist itself, rather than remaining a separate step nursing staff must
          remember to initiate.
        </p>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white shadow-sm p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Question</p>
        <p className="mb-2">According to the text, the sepsis-screening tool&rsquo;s benefit is:</p>
        <p className="mb-1">A. guaranteed regardless of when it is completed during admission.</p>
        <p className="mb-1">B. dependent on being completed at the point of admission.</p>
        <p className="mb-1">C. limited mainly by how quickly staff can be trained to use it.</p>
        <p>D. no longer being reviewed by the trust.</p>
      </div>

      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Eliminating A:</span> the text says the
        improvement &ldquo;largely disappeared&rdquo; when screening was delayed &mdash; the
        opposite of guaranteed regardless of timing.
      </p>
      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Eliminating C:</span> training speed is
        never mentioned anywhere in the extract &mdash; this option uses plausible-sounding
        vocabulary (&ldquo;staff,&rdquo; &ldquo;use it&rdquo;) that isn&rsquo;t actually connected
        to any claim in the text. This is the classic Part C trap: familiar words, no textual
        support.
      </p>
      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Eliminating D:</span> the text says the
        trust &ldquo;is now reviewing&rdquo; the checklist question &mdash; the opposite of no
        longer reviewing.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">B is correct</span> because it directly
        matches the sentence &ldquo;its usefulness depends entirely on being completed at the
        point of admission.&rdquo; Notice the process: each wrong option was checked against a
        specific sentence and rejected for a specific reason, not rejected on a vague feeling.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="common-mistakes" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        18 mistakes that quietly cost marks
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        None of these will make you fail obviously &mdash; they just chip away marks you assumed
        you had.
      </p>
      <ol className="list-decimal pl-5 space-y-3 text-gray-600 mb-4">
        <li><span className="font-semibold text-[#0F2356]">Reading every word of every Part A text before answering.</span> Burns most of your 15 minutes on content no question ever asks about.</li>
        <li><span className="font-semibold text-[#0F2356]">Reading the texts before the questions.</span> You end up scanning twice instead of once, with no idea what you&rsquo;re hunting for the first time.</li>
        <li><span className="font-semibold text-[#0F2356]">Paraphrasing Part A short answers.</span> A correct-meaning answer in your own words can still be marked wrong if it isn&rsquo;t the text&rsquo;s exact wording.</li>
        <li><span className="font-semibold text-[#0F2356]">Misspelling a copied answer.</span> Copying from memory instead of checking the text letter-by-letter loses marks you&rsquo;d already earned.</li>
        <li><span className="font-semibold text-[#0F2356]">Using outside clinical knowledge to answer.</span> The text is the only source of truth on the test, even if it contradicts your ward experience.</li>
        <li><span className="font-semibold text-[#0F2356]">Overthinking simple Part B questions.</span> Looking for a hidden trick in a straightforward workplace memo and talking yourself out of the obvious answer.</li>
        <li><span className="font-semibold text-[#0F2356]">Treating all 16 Part C questions as equally hard.</span> Spending five minutes on one difficult question instead of banking the easy ones first.</li>
        <li><span className="font-semibold text-[#0F2356]">Picking Part C options for familiar vocabulary.</span> A wrong option built from real words in the passage still needs to actually match what the passage claims.</li>
        <li><span className="font-semibold text-[#0F2356]">Not tracking the Part A clock separately.</span> Realising with two minutes left that six questions are still blank.</li>
        <li><span className="font-semibold text-[#0F2356]">Splitting the 45-minute block evenly between B and C.</span> Part C has more questions and denser text — it deserves more time, not an even split.</li>
        <li><span className="font-semibold text-[#0F2356]">Re-reading a Part C paragraph three or four times.</span> Usually a sign to guess and move on, not to keep pushing through.</li>
        <li><span className="font-semibold text-[#0F2356]">Leaving questions blank under time pressure.</span> A blank scores zero; an educated guess has real odds on a 3- or 4-option question.</li>
        <li><span className="font-semibold text-[#0F2356]">Ignoring headings and topic sentences in Part A.</span> They usually map directly onto the matching questions and save a full re-read.</li>
        <li><span className="font-semibold text-[#0F2356]">Confusing &ldquo;mentions X&rdquo; with &ldquo;recommends X&rdquo; in Part A matching.</span> Two different questions that a rushed reader answers identically.</li>
        <li><span className="font-semibold text-[#0F2356]">Second-guessing a confident first answer.</span> Changing a correct instinctive answer to a wrong one after overanalysing the options.</li>
        <li><span className="font-semibold text-[#0F2356]">Practising only untimed reading.</span> Untimed comprehension is a different skill from exam-paced scanning, and it doesn&rsquo;t transfer on its own.</li>
        <li><span className="font-semibold text-[#0F2356]">Practising only with general-topic articles.</span> Healthcare workplace documents (memos, policies, guidelines) have a different structure to news or academic writing, and Part B specifically expects familiarity with that structure.</li>
        <li><span className="font-semibold text-[#0F2356]">Never reviewing your wrong answers by question type.</span> Losing marks repeatedly in the same skill (say, Part C inference) without ever noticing the pattern.</li>
      </ol>

      {/* ---------------------------------------------------------- */}
      <h2 id="tutor-tips" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        Tips from experienced OET tutors
      </h2>
      <ul className="list-disc pl-5 space-y-3 text-gray-600 mb-4">
        <li>Time yourself by part, not just overall — knowing you consistently overrun Part C by four minutes is far more useful than knowing your total time was five minutes over.</li>
        <li>For Part A, read the question stem before you read any text. Decide what you&rsquo;re hunting for first.</li>
        <li>For Part C, read the whole text once before touching any question — answering question-by-question in a long text means re-reading the same passage repeatedly.</li>
        <li>Keep a running list of the specific reason you got each practice question wrong (wrong part, wrong skill, ran out of time) — after a few sessions a pattern usually appears.</li>
        <li>Practise with real workplace-style documents — hospital policy excerpts, patient information leaflets, incident report formats — not just news articles, since Part B specifically expects that register.</li>
        <li>Never leave a question blank in the final minute. A guess on a 3-option question is a 33% chance; a blank is a 0% chance.</li>
        <li>Don&rsquo;t chase a perfect score. Missing two or three of the hardest Part C questions while banking every Part A and B mark is a completely viable path to Grade B.</li>
        <li>When a Part C question asks for the writer&rsquo;s opinion rather than a fact, look for hedging language first (&ldquo;suggests,&rdquo; &ldquo;appears to,&rdquo; &ldquo;may indicate&rdquo;) — that&rsquo;s usually where the opinion lives, not in the factual sentences around it.</li>
        <li>Do a handful of practice sessions at a time of day close to your actual test slot. Reading speed under pressure genuinely dips at the end of a long shift or early in the morning — find that out in practice, not on test day.</li>
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
        <Link href="/learn/oet-listening" className="text-[#0F2356] font-semibold underline">
          OET Listening Guide for Nurses
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
      </div>

      <LearnCTA
        heading="Ready to beat the clock?"
        description="Free timed Reading passages with instant, part-by-part feedback — see exactly where the minutes and marks are going."
        href="/practice/reading"
        label="Start Free Reading Practice"
      />
    </main>
  )
}
