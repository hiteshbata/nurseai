import Link from 'next/link'
import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { SummaryBox } from '@/components/learn/SummaryBox'
import { Callout } from '@/components/learn/Callout'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET Writing Guide for Nurses: How to Pass the OET Writing Sub-Test'
const DESCRIPTION =
  'A complete OET Writing guide for nurses: the format, all six assessment criteria explained with real letter examples, a minute-by-minute exam strategy, a full worked example, and the mistakes that quietly cap most candidates’ scores.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/learn/oet-writing' },
}

const toc = [
  { id: 'what-is-oet-writing', label: 'What is OET Writing?' },
  { id: 'format', label: 'The format' },
  { id: 'assessment-criteria', label: 'The 6 assessment criteria' },
  { id: 'step-by-step-strategy', label: 'A minute-by-minute exam strategy' },
  { id: 'worked-example', label: 'A full worked example' },
  { id: 'common-mistakes', label: '18 mistakes that quietly cap your score' },
  { id: 'tutor-tips', label: 'Tips from experienced OET tutors' },
  { id: 'faq', label: 'Frequently asked questions' },
  { id: 'related-guides', label: 'Related guides' },
]

const faqs = [
  {
    q: 'How long is the OET Writing sub-test?',
    a: '45 minutes in total. The first 5 minutes are reading time for the case notes and task instructions — in the paper-based test you cannot write on the answer sheet during this window, only annotate the stimulus. The remaining 40 minutes are for planning and writing your letter.',
  },
  {
    q: 'Do I need exactly 180–200 words?',
    a: 'There is no hard word-count rule enforced by OET, but 180–200 words is the length examiners are calibrated to expect for a well-organised, appropriately concise letter. Much shorter and you risk missing required content; much longer and you’re usually being marked down on Conciseness for including irrelevant detail.',
  },
  {
    q: 'What letter types can come up in the nursing Writing task?',
    a: 'Most commonly a referral letter (to a specialist, GP, or community service), but discharge letters, transfer letters, and letters to a patient or carer also appear. The reader changes each time, which is exactly what the Genre & Style criterion is testing — the same content needs a different register depending on who’s reading it.',
  },
  {
    q: 'Is OET Writing marked by a computer or a human?',
    a: 'By trained human examiners using OET’s official assessment criteria and level descriptors, not automated scoring. That’s also why two letters with similar vocabulary can score very differently — the criteria reward accurate, well-organised clinical content, not just fluent English.',
  },
  {
    q: 'What happens if I run out of time before finishing the letter?',
    a: 'An incomplete letter is scored on what’s there — missing closing content usually costs you on Purpose and Organisation & Layout, since the reader is left without a clear final request or sign-off. This is why experienced candidates secure the opening and closing lines early rather than leaving them for the end.',
  },
  {
    q: 'Can I use medical abbreviations in my letter?',
    a: 'Only ones the specific reader would recognise. Writing to another clinician, common clinical abbreviations are usually fine; writing to a patient or their family, the same abbreviations read as jargon and cost you marks on Genre & Style. Match the abbreviation to the reader named in the task, not to your own habits.',
  },
  {
    q: 'What’s a good OET Writing score for nurses?',
    a: 'Most regulators, including the UK NMC, ask for at least Grade B (350/500) in Writing, same as the other three sub-tests. Requirements vary by regulator and do change, so confirm your target country’s current number with our score calculator or the official OET site before you sit the test.',
  },
  {
    q: 'Can I fail Writing while passing Listening, Reading, and Speaking?',
    a: 'Yes. Each of the four sub-tests is graded independently, and most regulators set a minimum grade for every one of them. Writing is graded on structure and clinical judgement as much as language, so strong spoken English doesn’t automatically transfer into a strong Writing score.',
  },
  {
    q: 'How is OET Writing different from IELTS Writing?',
    a: 'IELTS Writing Task 1 asks you to describe data or a general process; OET Writing asks you to write a real clinical letter from case notes, in your own profession. If you’re deciding between the two tests, see our full OET vs IELTS comparison.',
  },
  {
    q: 'Do I need real clinical experience to score well?',
    a: 'You need to be able to read and interpret case notes accurately — which nursing training and ward experience gives you — but you don’t need advanced medical knowledge beyond what’s in the notes. The test is checking communication and judgement about what to include, not diagnostic ability.',
  },
  {
    q: 'Can I plan my letter on the case notes paper before writing?',
    a: 'Yes — annotating the stimulus (underlining, circling, crossing out irrelevant history) during reading time is normal practice and recommended. What you can’t do in the paper-based test is start writing sentences on the answer sheet before the 40-minute writing time begins.',
  },
  {
    q: 'Is the Writing sub-test the same for OET@Home and the paper-based test?',
    a: 'The task format and criteria are the same; only the delivery method changes (typed on-screen for OET@Home, handwritten for the paper-based test). Always check current delivery options and rules on the official OET website, as these are set and updated by OET, not by us.',
  },
]

export default function OetWritingPillarPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd
        path="/learn/oet-writing"
        title={TITLE}
        description={DESCRIPTION}
        datePublished="2026-07-27"
      />

      <Link href="/blog" className="text-sm text-gray-500 hover:text-[#0F2356] transition">
        ← All articles
      </Link>
      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">
        OET Writing Guide for Nurses
      </h1>
      <p className="text-gray-500 text-lg mb-2">
        Everything a nurse needs to pass OET Writing: the format, all six assessment criteria
        with real examples, a minute-by-minute strategy, a full worked example, and the mistakes
        that quietly cap most candidates&rsquo; scores.
      </p>
      <ArticleMeta date="2026-07-27" />

      <p className="text-gray-600 leading-relaxed mb-6">
        If you&rsquo;ve sat OET Writing before and come away thinking &ldquo;my English is fine,
        so why did I only get a C+?&rdquo; &mdash; this guide is for you. Writing is the sub-test
        where strong spoken English stops being enough, because the examiner isn&rsquo;t just
        reading your grammar. They&rsquo;re reading whether you can take a page of messy case
        notes and turn it into a letter a stranger could safely act on in under a minute. That&rsquo;s
        a specific, learnable skill, and most candidates have never been taught it directly. We
        have &mdash; this is everything we&rsquo;d tell you in a one-to-one lesson.
      </p>

      <SummaryBox
        rows={[
          { label: 'Time', value: '45 minutes (5 min reading + 40 min writing)' },
          { label: 'Marks', value: 'Graded A–E, 0–500 scale' },
          { label: 'Parts', value: '1 task, 1 letter, based on case notes' },
          { label: 'Difficulty', value: 'Moderate–high (language + clinical judgement)' },
          { label: 'Passing grade', value: 'Usually Grade B / 350 — confirm with your regulator' },
          { label: 'Who this is for', value: 'Any nurse preparing for OET, especially repeat candidates' },
        ]}
      />

      <TableOfContents items={toc} />

      {/* ---------------------------------------------------------- */}
      <h2 id="what-is-oet-writing" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What is OET Writing?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Writing is a 45-minute task where you read a set of case notes about a patient and
        write a letter based on them &mdash; almost always to another healthcare professional, but
        sometimes to a patient or their family. There&rsquo;s no choice of topic and nothing to
        memorise in advance: the case notes are new to you on the day, and your letter has to be
        built from them, in your own words, under time pressure.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        Think about what actually happens at handover on a busy ward. A colleague hands you a
        summary of a patient you&rsquo;ve never met, and you need to understand, within seconds,
        what matters: what happened, what&rsquo;s outstanding, what you need to watch for. A good
        handover note gives you exactly that. A bad one buries the important line (&ldquo;still
        due a repeat potassium&rdquo;) somewhere in the middle of three paragraphs about the
        patient&rsquo;s admission four days ago. OET Writing is testing whether you can produce the
        good version, under exam conditions, for a reader who has never seen this patient before.
      </p>
      <Callout variant="tip" title="Why this trips up strong English speakers">
        Candidates who read and speak English fluently often assume Writing will be their easiest
        sub-test. It frequently isn&rsquo;t, because the criteria reward judgement about what to
        include and how to organise it — skills that have nothing to do with vocabulary range.
        A grammatically simple letter that includes the right facts in the right order outscores a
        beautifully written letter that buries or omits them.
      </Callout>

      {/* ---------------------------------------------------------- */}
      <h2 id="format" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        The format
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Every nursing Writing task follows the same shape: case notes, a set of task instructions
        telling you who to write to and why, and a blank answer sheet (or text box, for
        OET@Home). Here&rsquo;s how the 45 minutes are structured:
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Phase</th>
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Time</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What you do</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4">Reading time</td>
              <td className="py-2 pr-4">5 minutes</td>
              <td className="py-2">Read the task instructions and case notes; annotate, don&rsquo;t write sentences yet.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4">Writing time</td>
              <td className="py-2 pr-4">40 minutes</td>
              <td className="py-2">Plan briefly, then write your letter in full.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Total</td>
              <td className="py-2 pr-4 font-semibold text-[#0F2356]">45 minutes</td>
              <td className="py-2">One task, one letter, no second attempt.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">The letter types</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        The task rotates between a few letter types, and each one changes who your reader is and
        what tone you need:
      </p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">Referral letter</span> &mdash; to a
          specialist, GP, or community service, asking them to take over or contribute to a
          patient&rsquo;s care.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Discharge/transfer letter</span> &mdash;
          summarising an admission for whoever continues care next, in hospital or the community.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Letter to a patient or carer</span> &mdash;
          same clinical accuracy, but in plain language, since the reader isn&rsquo;t medically
          trained.
        </li>
      </ul>
      <p className="text-gray-600 leading-relaxed mb-4">
        You won&rsquo;t know which one you&rsquo;ll get until you open the case notes, which is why
        memorising one fixed letter (one opening sentence, one structure) is risky &mdash; it fits
        some tasks and visibly doesn&rsquo;t fit others.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">What examiners expect</h3>
      <p className="text-gray-600 leading-relaxed mb-4">
        Examiners are trained to read your letter the way your named reader would: someone who has
        never met this patient and needs to act on your letter safely. In practice, that means
        they&rsquo;re checking for a clear reason for writing, accurate content taken from the case
        notes, appropriate tone for that reader, logical organisation, and clean-enough language
        that none of the above gets lost. All six of the official criteria below map directly onto
        that reader&rsquo;s experience.
      </p>

      <LearnCTA
        heading="See how your own letter would score"
        description="Write a full referral or discharge letter from real case notes and get instant, criteria-by-criteria feedback from SpeakOET's AI examiner."
        href="/practice/writing"
        label="Try OET Writing Practice"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="assessment-criteria" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        The 6 assessment criteria
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET scores your letter against six official criteria. Purpose is scored out of 3; the
        other five are each scored out of 7, for a raw total out of 38, which converts to your
        letter grade and 0–500 score. Knowing these six by name &mdash; and what an examiner
        is actually looking for in each &mdash; is the single biggest lever you have, because it
        turns &ldquo;write a good letter&rdquo; into six concrete, practisable checks.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">1. Purpose (Overall Task Fulfilment)</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Does your letter make clear, immediately, why you&rsquo;re writing &mdash; and does it
        restate that purpose as a specific request near the end? Examiners can tell within one
        sentence whether an opening is tailored to this patient or lifted from a template you
        rehearsed at home. A generic opening that would fit any letter caps this criterion at 2 out
        of 3, no matter how well the rest is written.
      </p>
      <Callout variant="good" title="Tailored opening">
        &ldquo;I am writing to refer Mr. Kumar to your Community Diabetes Team for further
        management of his glycaemic control, following a recent admission with pneumonia during
        which his blood glucose became difficult to control.&rdquo;
      </Callout>
      <Callout variant="bad" title="Generic, memorised opening">
        &ldquo;I am writing to refer this patient to you for further assessment and management.&rdquo;
        Grammatically fine, but it says nothing specific to this case &mdash; it would fit any
        referral letter for any patient.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> build your opening
        from two things pulled from the actual case notes &mdash; the patient&rsquo;s name and the
        specific clinical reason &mdash; and close with a specific ask (&ldquo;please review and
        advise on further management&rdquo;), not a vague sign-off.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">2. Content</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Everything the reader needs to safely continue care, accurately represented, with nothing
        important left out. This is judged directly against the case notes in front of the
        examiner, so any change of meaning when you paraphrase counts against you &mdash; even a
        small one.
      </p>
      <Callout variant="bad" title="A tense slip that changes meaning">
        Case notes say &ldquo;metformin added.&rdquo; Writing &ldquo;metformin will be added&rdquo;
        tells the reader the medication hasn&rsquo;t started yet, when it already has &mdash; a
        real patient-safety error, not just a grammar point.
      </Callout>
      <Callout variant="good" title="Accurate paraphrase">
        &ldquo;Metformin 500mg twice daily was commenced during admission for newly diagnosed type
        2 diabetes.&rdquo; Same information, correct tense, nothing added or lost.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> before you write a
        single sentence, list every &ldquo;must include&rdquo; fact from the case notes on scrap
        paper or in your head &mdash; diagnosis, medications, allergies, relevant social context,
        and what happens next. Tick each one off as you draft so nothing gets dropped under time
        pressure.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">3. Conciseness &amp; Clarity</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        The right length for this case and this reader, with no irrelevant information, and
        everything summarised rather than copied wholesale from the notes. This is the criterion
        that punishes candidates who panic and include everything &ldquo;just in case.&rdquo;
      </p>
      <Callout variant="bad" title="Irrelevant detail included">
        A discharge letter about a chest infection that spends a sentence on the patient&rsquo;s
        hobbies or unrelated family history from years earlier. It might be true and it might be in
        the case notes, but the receiving GP doesn&rsquo;t need it to act on this admission.
      </Callout>
      <Callout variant="good" title="Grouped and summarised">
        All three current medications listed together in one sentence, rather than scattered
        across three separate paragraphs in the order they happened to appear in the case notes.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> for every sentence
        you write, ask &ldquo;does the person reading this need it to do their job?&rdquo; If the
        honest answer is no, cut it &mdash; even if it&rsquo;s interesting, even if it&rsquo;s true.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">4. Genre &amp; Style</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Formal, factual, and appropriate to whoever you&rsquo;re writing to. Clinical language for
        a clinician, plain language for a patient or family member, and a neutral tone throughout
        &mdash; facts, not judgements, about the patient.
      </p>
      <Callout variant="bad" title="Judgemental label, informal contraction">
        &ldquo;Please note the patient didn&rsquo;t take his meds as advised and is a heavy
        drinker.&rdquo; A contraction, and two labels (&ldquo;didn&rsquo;t,&rdquo; &ldquo;heavy
        drinker&rdquo;) that pass judgement instead of stating facts.
      </Callout>
      <Callout variant="good" title="Neutral, formal facts">
        &ldquo;The patient reports missing several doses of his prescribed medication and
        currently drinks approximately 40 units of alcohol per week.&rdquo; Same information,
        stated as fact, no contractions, no judgement.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> write &ldquo;did
        not,&rdquo; never &ldquo;didn&rsquo;t&rdquo;; describe behaviour in numbers and facts
        instead of labels; and only use an abbreviation if the specific reader named in your task
        would already know it.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">5. Organisation &amp; Layout</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        A logical order &mdash; chronological or thematic &mdash; with the most important
        information first, related ideas grouped into paragraphs, and a layout (salutation, body,
        closing) the reader can scan quickly. This is scored separately from Content, so accurate
        facts in the wrong order still lose marks here.
      </p>
      <Callout variant="bad" title="Copying the case-note order">
        A letter that walks through the case notes exactly as they were presented &mdash; admission
        date, then day 1, day 2, day 3 &mdash; regardless of what actually matters for the reader,
        so the one thing they need to act on is buried on the last line.
      </Callout>
      <Callout variant="good" title="Grouped by theme, most important first">
        Paragraph 1: reason for referral and current status. Paragraph 2: relevant history and
        medications. Paragraph 3: what&rsquo;s needed next. The reader gets the headline first,
        detail second.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> before writing,
        sort your case-note facts into 3–4 themed groups rather than writing them in the order
        they&rsquo;re printed on the page. The case notes are a source of facts, not an outline.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">6. Language</h3>
      <p className="text-gray-600 leading-relaxed mb-3">
        Grammar, vocabulary, spelling, and punctuation, judged by whether an error causes the
        reader real strain or confusion &mdash; not by counting every minor slip. A missing article
        rarely costs you anything; an error that changes clinical meaning costs you a lot.
      </p>
      <Callout variant="bad" title="A dropped word that changes meaning">
        &ldquo;She has a history of penicillin allergy&rdquo; when the notes say the opposite
        &mdash; a single missing &ldquo;no&rdquo; turns a safety warning into a dangerous
        instruction to ignore.
      </Callout>
      <Callout variant="good" title="Minor error, meaning intact">
        &ldquo;Patient was discharge home with follow-up arranged&rdquo; &mdash; a grammar slip an
        examiner will note, but the meaning is completely unaffected.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">How to improve:</span> spend your last few
        minutes proofreading specifically for negations, numbers, units, and dosages &mdash; the
        handful of words where an error is actually dangerous, not just untidy.
      </p>

      <LearnCTA
        heading="Practise against all 6 criteria"
        description="SpeakOET's AI examiner scores every letter against Purpose, Content, Conciseness, Genre & Style, Organisation, and Language — the same six criteria above."
        href="/practice/writing"
        label="Write Your First Letter Free"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="step-by-step-strategy" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A minute-by-minute exam strategy
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        &ldquo;Manage your time&rdquo; is useless advice on its own. Here&rsquo;s exactly what to
        do with each of the 45 minutes, based on how the highest-scoring candidates actually work
        through the task.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Minute</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What to do</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">0–2</td>
              <td className="py-2">Read the task instructions first, not the case notes. Note who the reader is and the letter type &mdash; this decides your tone before you&rsquo;ve seen a single case-note detail.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">2–5</td>
              <td className="py-2">Read the case notes once for overall shape, then again with a pen: circle the presenting complaint, box relevant history, cross out anything clearly irrelevant to this reader.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">5–10</td>
              <td className="py-2">Group your circled facts into 3–4 paragraph themes. Don&rsquo;t write full sentences yet &mdash; a one-word label per paragraph is enough.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">10–15</td>
              <td className="py-2">Write your opening and closing lines first, even before the body. This locks in your Purpose score even if you run short on time later.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">15–40</td>
              <td className="py-2">Write the body paragraphs from your groupings. Aim for 180–200 words total across 4–5 paragraphs &mdash; roughly 35–45 words each.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">40–45</td>
              <td className="py-2">Proofread for negations, numbers, dosages, and contractions only &mdash; not a full re-read. Check the word count is in range.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout variant="warning" title="If you freeze on the opening line">
        Don&rsquo;t sit staring at a blank first sentence. Skip it, start the body with the most
        concrete fact from the case notes, and come back to the opening in your last five minutes.
        Examiners score whether the features are present in the letter, not the order you wrote
        them in.
      </Callout>
      <Callout variant="warning" title="If you&rsquo;re running out of time">
        Protect a rushed-but-complete closing line (&ldquo;please contact me if further information
        is required&rdquo;) over polishing an earlier paragraph. A letter that stops mid-thought
        reads as poorly organised even if every sentence before it was strong.
      </Callout>

      {/* ---------------------------------------------------------- */}
      <h2 id="worked-example" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A full worked example
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Here&rsquo;s a realistic (invented) case-notes stimulus, followed by the thinking a
        strong candidate does before writing a single sentence of the letter itself.
      </p>

      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Case notes (extract)</p>
        <p className="mb-1">Patient: Rajesh Kumar, 58</p>
        <p className="mb-1">Admitted with community-acquired pneumonia, day 5 of 5-day IV antibiotic course, now stepped down to oral antibiotics</p>
        <p className="mb-1">PMH: Type 2 diabetes (diet-controlled), hypertension (amlodipine 5mg OD)</p>
        <p className="mb-1">Course: required a short course of oral steroids for wheeze; blood glucose transiently elevated during admission, now settling</p>
        <p className="mb-1">Social: lives alone, daughter visits weekly</p>
        <p className="mb-1">Task: write a discharge letter to the patient&rsquo;s GP. Include follow-up chest X-ray in 6 weeks and advise on monitoring blood glucose given the steroid course.</p>
      </div>

      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">What a strong candidate notices first:</span>{' '}
        the steroid detail is easy to skim past because it reads like background, but it&rsquo;s
        actually the reason the task explicitly asks about glucose monitoring. Missing that
        connection means missing the point of the letter &mdash; a Content error, not a language
        one. This is exactly the kind of detail the Content criterion is built to catch.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        <span className="font-semibold text-[#0F2356]">Paragraph plan:</span> (1) reason for
        writing + admission summary, (2) relevant background — diabetes, hypertension, steroid
        course and its effect on glucose, (3) discharge medications and what&rsquo;s needed next
        (X-ray, glucose monitoring), (4) closing request.
      </p>

      <div className="rounded-xl border border-gray-100 bg-white shadow-sm p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Letter (188 words)</p>
        <p className="mb-3">Dear Dr. Sharma,</p>
        <p className="mb-3">
          I am writing to inform you of Mr. Rajesh Kumar&rsquo;s recent discharge following
          admission for community-acquired pneumonia, so that you can continue his follow-up
          care in the community.
        </p>
        <p className="mb-3">
          Mr. Kumar, 58, was admitted for a 5-day course of intravenous antibiotics, which he has
          now completed, stepping down to oral antibiotics to finish at home. He has a background
          of diet-controlled type 2 diabetes and hypertension, managed with amlodipine 5mg once
          daily. During admission he required a short course of oral steroids for associated
          wheeze, which caused a transient rise in his blood glucose; this has since begun to
          settle but has not yet been confirmed as fully resolved.
        </p>
        <p className="mb-3">
          Given this, I would be grateful if you could arrange blood glucose monitoring over the
          coming weeks to confirm it has returned to his usual baseline. He also requires a
          follow-up chest X-ray in approximately 6 weeks to confirm radiological resolution. Mr.
          Kumar lives alone, though his daughter visits weekly and is aware of his current
          condition.
        </p>
        <p className="mb-3">
          Please do not hesitate to contact the ward if you require any further information.
        </p>
        <p>Yours sincerely,</p>
      </div>

      <p className="text-gray-600 leading-relaxed mb-4">
        Notice what&rsquo;s absent as much as what&rsquo;s present: no description of the
        patient&rsquo;s day-by-day observations chart, nothing about how he felt about being in
        hospital, no restating of information the GP doesn&rsquo;t need. Every sentence earns its
        place against one of the six criteria &mdash; that&rsquo;s the discipline the test is
        actually rewarding.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="common-mistakes" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        18 mistakes that quietly cap your score
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Most of these won&rsquo;t make your letter unreadable &mdash; which is exactly why they
        survive candidates&rsquo; own proofreading. They cap a score that otherwise looks fine.
      </p>
      <ol className="list-decimal pl-5 space-y-3 text-gray-600 mb-4">
        <li>
          <span className="font-semibold text-[#0F2356]">A memorised opening sentence.</span>{' '}
          It fits every task equally well, which is exactly the problem &mdash; examiners are
          trained to spot template openings that aren&rsquo;t tailored to this patient.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">No closing request.</span> Ending with a
          summary instead of a specific ask (&ldquo;please review,&rdquo; &ldquo;please arrange
          follow-up&rdquo;) leaves Purpose only half-answered.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Writing in case-note order instead of importance order.</span>{' '}
          Chronological is not the same as logical &mdash; the reader needs the headline first.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Changing tense when paraphrasing.</span>{' '}
          &ldquo;Will be started&rdquo; instead of &ldquo;was started&rdquo; silently changes
          whether treatment has actually begun.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Dropping a qualifier.</span> Omitting
          that a cast &ldquo;has since been removed&rdquo; leaves the reader thinking it&rsquo;s
          still in place.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Including irrelevant social history.</span>{' '}
          A patient&rsquo;s hobbies or unrelated old history read as padding, not evidence of
          thoroughness.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Writing well over 200 words.</span> Length
          alone isn&rsquo;t a Content strength &mdash; past a point it signals you couldn&rsquo;t
          summarise, which is Conciseness working against you.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Writing well under 150 words.</span>{' '}
          Usually means required content got left out entirely, not just compressed.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Contractions.</span> &ldquo;Didn&rsquo;t,&rdquo;
          &ldquo;won&rsquo;t,&rdquo; &ldquo;can&rsquo;t&rdquo; read as informal in a clinical
          letter &mdash; write them in full.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Judgemental labels instead of facts.</span>{' '}
          &ldquo;Non-compliant&rdquo; or &ldquo;heavy drinker&rdquo; instead of the actual figures
          from the notes.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Jargon for a lay reader.</span> Using
          ward abbreviations in a letter addressed to a patient or family member, who won&rsquo;t
          recognise them.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">One giant paragraph.</span> No visual
          structure makes even accurate content look disorganised at a glance.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">No salutation or closing.</span> Missing
          &ldquo;Dear Dr. X&rdquo; or &ldquo;Yours sincerely&rdquo; costs Organisation & Layout
          marks for no good reason.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Missing a negation.</span> &ldquo;Has a
          history of&rdquo; instead of &ldquo;has no history of&rdquo; is one dropped word with a
          dangerous meaning change.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Mixing up dosage figures.</span> A
          transposed number in a medication dose is a language slip with a clinical consequence.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Spending too long reading, not enough writing.</span>{' '}
          An unfinished letter loses far more than a slightly rougher, but complete, one.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Ignoring a specific task instruction.</span>{' '}
          If the task says &ldquo;advise on follow-up for X,&rdquo; a letter that&rsquo;s otherwise
          excellent but never mentions X has not fulfilled the purpose.
        </li>
        <li>
          <span className="font-semibold text-[#0F2356]">Practising only referral letters.</span>{' '}
          Discharge, transfer, and patient letters each need a different structure and tone &mdash;
          practising one type leaves you unprepared for the others.
        </li>
      </ol>

      {/* ---------------------------------------------------------- */}
      <h2 id="tutor-tips" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        Tips from experienced OET tutors
      </h2>
      <ul className="list-disc pl-5 space-y-3 text-gray-600 mb-4">
        <li>
          Build 2–3 flexible opening &ldquo;shapes&rdquo; with blanks to fill in from the case
          notes, rather than one fixed sentence. A shape survives contact with an unfamiliar task;
          a memorised sentence doesn&rsquo;t.
        </li>
        <li>
          Time your practice attempts in the same phases as the real test &mdash; reading,
          planning, opening/closing, body, proofread &mdash; not just a single 45-minute countdown.
          You want to know which phase you personally overrun.
        </li>
        <li>
          Read your finished letter out loud once during practice. Your eyes skip over missing
          words when reading silently; your ear usually doesn&rsquo;t.
        </li>
        <li>
          Keep a short personal list of words you tend to slip into under pressure (contractions,
          labels like &ldquo;non-compliant&rdquo;) and scan for exactly those in your last minute
          of proofreading.
        </li>
        <li>
          Practise all the letter types that can appear — referral, discharge/transfer, and
          patient/carer &mdash; not just the one you find easiest.
        </li>
        <li>
          Get feedback measured against the six named criteria, not general impressions.
          &ldquo;Sounds good&rdquo; from a friend doesn&rsquo;t tell you whether you lost marks on
          Organisation or Content.
        </li>
        <li>
          When a case note detail seems oddly specific (a steroid course, a recent fall, a
          discontinued medication), assume it&rsquo;s there on purpose. Task-writers rarely include
          detail with no bearing on what you&rsquo;re asked to do.
        </li>
      </ul>

      <p className="text-gray-600 leading-relaxed mb-8">
        Always check the exact current task format, timing, and marking guide on the official OET
        website &mdash; those details are set and occasionally updated by OET, not by us.
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
        heading="Ready to write your first letter?"
        description="Free AI-generated case notes, an instant score against all 6 official criteria, and detailed feedback on exactly what to fix."
        href="/practice/writing"
        label="Start Free Writing Practice"
      />
    </main>
  )
}
