import Link from 'next/link'
import type { Metadata } from 'next'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { TableOfContents } from '@/components/learn/TableOfContents'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { SummaryBox } from '@/components/learn/SummaryBox'
import { Callout } from '@/components/learn/Callout'
import { FaqSection } from '@/components/seo/FaqSection'
import { OetPageJsonLd } from '@/components/seo/OetPageJsonLd'

const TITLE = 'OET Speaking: The Complete Guide for Nurses'
const DESCRIPTION =
  'Everything a nurse needs to know about OET Speaking: the two roleplays, all 9 assessment criteria explained with real examples, a full worked roleplay, common mistakes, and how to prepare.'

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: '/oet/speaking' },
}

const toc = [
  { id: 'what-is-oet-speaking', label: 'What is OET Speaking?' },
  { id: 'format', label: 'The format' },
  { id: 'criteria', label: 'All 9 assessment criteria' },
  { id: 'step-by-step-strategy', label: 'A step-by-step exam strategy' },
  { id: 'worked-example', label: 'A full worked example' },
  { id: 'common-mistakes', label: '18 mistakes that quietly cap your score' },
  { id: 'tutor-tips', label: 'Tips from experienced OET tutors' },
  { id: 'faq', label: 'Frequently asked questions' },
  { id: 'related-guides', label: 'Related guides' },
]

const faqs = [
  {
    q: 'What is the OET Speaking sub-test?',
    a: "OET Speaking is a face-to-face (or video-call) roleplay test taken separately from Listening, Reading, and Writing. You play yourself as a nurse; a trained interlocutor plays a patient or relative. It's profession-specific, so nurses get nursing scenarios, and it's recorded for two examiners to assess afterwards.",
  },
  {
    q: 'How is OET Speaking scored?',
    a: 'Two examiners independently score your recording against 9 criteria, split into linguistic criteria (intelligibility, fluency, appropriateness of language, resources of grammar and expression) and clinical communication criteria (relationship building, understanding the patient’s perspective, providing structure, information gathering, information giving). Scores convert to a 0–500 scale and a letter grade A–E.',
  },
  {
    q: 'How long is the OET Speaking test?',
    a: 'About 20 minutes total: two roleplays of roughly 5 minutes each, with about 2–3 minutes to read each card before you start. The exact timing is set by OET, so confirm current figures on the official site before your test date.',
  },
  {
    q: 'What’s a good OET Speaking score for nurses?',
    a: 'Most regulators, including the UK NMC, ask for at least Grade B (350/500). See our full breakdown of score requirements by regulator, or check your target country’s exact number with the score calculator.',
  },
  {
    q: 'Can I fail Speaking while passing the other three sub-tests?',
    a: 'Yes — each of the four sub-tests is graded independently, and most regulators set a minimum for every one of them. A strong Writing or Reading score does not compensate for a weak Speaking score.',
  },
  {
    q: 'Is the interlocutor a real patient or an actor?',
    a: 'A trained interlocutor, not a real patient — but they play the role convincingly and improvise around the scenario rather than reading from a script. Treat them exactly as you would a real, anxious patient or relative, because that improvisation is exactly what the clinical communication criteria are assessing.',
  },
  {
    q: 'Can I ask the interlocutor to repeat something?',
    a: "Yes, and doing so naturally — 'sorry, could you say that again?' — costs you nothing. It's a completely normal thing to say to a real patient too, and examiners are listening for how you communicate, not for a flawless first-time hearing.",
  },
  {
    q: 'Do I get to choose which two roleplays I do?',
    a: "No, the two scenarios are assigned to you as part of the test. They're drawn from realistic nursing situations, so broad familiarity with common ward, clinic, and community scenarios matters more than trying to predict the exact topic in advance.",
  },
  {
    q: 'What happens if I run out of things to say?',
    a: "A short pause to think is completely normal and won't cost you marks on its own — real conversations have pauses. What does cost you is going silent for so long the interlocutor has to rescue the conversation, or panicking and abandoning the card's remaining points altogether.",
  },
  {
    q: 'Is OET Speaking harder than IELTS Speaking?',
    a: "They test different skills. IELTS Speaking is an interview about general topics and opinions; OET Speaking is a roleplay where you perform your actual job — explaining, reassuring, gathering information — in character. Most nurses find OET Speaking more natural once they stop treating it like an English interview. See our full OET vs IELTS comparison for more.",
  },
  {
    q: 'How can I practise OET Speaking without a study partner?',
    a: 'Roleplay practice is the one part of OET prep that’s genuinely hard to do alone, since you need someone improvising as the patient. An AI patient that responds in real time and scores you against the 9 criteria solves that — that’s exactly what SpeakOET’s speaking practice does.',
  },
  {
    q: 'Is OET@Home Speaking different from the in-person test?',
    a: 'The format and criteria are identical; only the delivery changes (a live video call for OET@Home, face-to-face with an interlocutor for the in-person test). Always confirm current delivery options on the official OET website, since these are set by OET, not by us.',
  },
]

export default function OetSpeakingPillarPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <OetPageJsonLd
        path="/oet/speaking"
        title={TITLE}
        description={DESCRIPTION}
        datePublished="2026-07-29"
      />

      <h1 className="text-3xl font-bold text-[#0F2356] mt-4 mb-4">
        OET Speaking: The Complete Guide for Nurses
      </h1>
      <p className="text-gray-500 text-lg mb-2">
        The format, all 9 assessment criteria with real examples, a full worked roleplay, common
        mistakes, and how to prepare &mdash; in one place.
      </p>
      <ArticleMeta date="2026-07-29" />

      <p className="text-gray-600 leading-relaxed mb-6">
        If you&rsquo;ve sat OET Speaking before and walked out thinking &ldquo;I talked the whole
        time, why wasn&rsquo;t that enough?&rdquo; &mdash; you&rsquo;ve already found the thing
        that trips up most candidates. Speaking isn&rsquo;t judging whether you can hold a
        conversation in English. It&rsquo;s judging whether you can run a clinical conversation
        &mdash; structured, reactive, patient-centred &mdash; while also speaking clearly. Most
        candidates prepare for the language half and never train the other half at all.
      </p>

      <SummaryBox
        rows={[
          { label: 'Time', value: '~20 minutes (2 roleplays, ~5 min each + prep)' },
          { label: 'Marks', value: '9 criteria, converts to Grade A–E, 0–500 scale' },
          { label: 'Parts', value: '2 roleplays with a trained interlocutor' },
          { label: 'Difficulty', value: 'High — live, unscripted, no second take' },
          { label: 'Passing grade', value: 'Usually Grade B / 350 — confirm with your regulator' },
          { label: 'Who this is for', value: 'Nurses nervous about live roleplay, or repeat candidates' },
        ]}
      />

      <div className="mt-6 mb-8 rounded-2xl border border-gray-100 bg-[#F8FAFC] p-6 text-center">
        <p className="text-[#0F2356] font-semibold mb-3">
          The fastest way to understand OET Speaking is to do one.
        </p>
        <Link
          href="/practice/speaking"
          className="inline-flex items-center justify-center bg-[#10B981] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#0ea472] transition-colors"
        >
          Try a Free Roleplay Now
        </Link>
      </div>

      <TableOfContents items={toc} />

      {/* ---------------------------------------------------------- */}
      <h2 id="what-is-oet-speaking" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        What is OET Speaking?
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Speaking tests the exact conversation you have dozens of times a shift &mdash;
        explaining a procedure to a nervous patient, gathering a history from someone in pain,
        reassuring a relative without over-promising. It isn&rsquo;t a general English speaking
        test with a medical topic bolted on; it&rsquo;s a simulation of your actual job, recorded
        and scored against how real clinical communication is supposed to work.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        That&rsquo;s why fluent, confident English speakers still sometimes score lower than
        expected. Talking smoothly for five minutes isn&rsquo;t the target &mdash; structuring the
        conversation, picking up on what the patient actually says, and checking they&rsquo;ve
        understood are all scored separately from how clearly you pronounce your words.
      </p>
      <Callout variant="tip" title="Why confident speakers still lose marks">
        A nurse who talks fluently but delivers a memorised, one-directional explanation without
        pausing to check the patient&rsquo;s understanding can score well on the linguistic
        criteria and still lose marks across most of the clinical communication criteria &mdash;
        which make up 60% of your final band.
      </Callout>
      <p className="text-gray-600 leading-relaxed mb-4">
        It also plays out very differently from a general English speaking test. IELTS Speaking is
        an interview: an examiner asks you questions about your life, your opinions, a familiar
        topic, and you answer as yourself. OET Speaking is a roleplay: you stay in character as
        the nurse for the full five minutes, the &ldquo;examiner&rdquo; is acting as a patient who
        might get upset, go off-topic, or push back, and you&rsquo;re expected to manage that the
        way you would on a real ward. Candidates who prepare as if it&rsquo;s an interview tend to
        answer questions well but struggle to drive the conversation themselves.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="format" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        The format
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        OET Speaking is taken separately from the other three sub-tests, usually on a different
        day. You sit with a trained interlocutor &mdash; in person or over video for OET@Home
        &mdash; and complete two roleplays, each about 5 minutes long. Before each one you get
        roughly 2&ndash;3 minutes to read a card describing the scenario: who you are, who the
        patient or relative is, and the points you need to cover.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        The interlocutor plays the patient and improvises around the scenario rather than
        following a script, so the conversation genuinely depends on what you say. Both roleplays
        are recorded and sent to two independent examiners, who each score you against the same 9
        criteria. Your final grade is the average of the two.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Stage</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What happens</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Prep time</td>
              <td className="py-2">~2–3 minutes to read the card and plan, per roleplay.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Roleplay 1</td>
              <td className="py-2">~5 minutes with the interlocutor, recorded.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Roleplay 2</td>
              <td className="py-2">~5 minutes, a different scenario, recorded.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Assessment</td>
              <td className="py-2">Two examiners independently score both recordings later.</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ---------------------------------------------------------- */}
      <h2 id="criteria" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        All 9 assessment criteria
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Examiners score you against two groups of criteria, each 0&ndash;6. Knowing them by name
        changes how you practise &mdash; instead of vaguely &ldquo;sounding fluent,&rdquo; you can
        target the exact thing losing you marks.
      </p>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">Clinical communication criteria (60% of your band)</h3>

      <p className="text-gray-600 leading-relaxed mb-2 font-semibold text-[#0F2356]">1. Relationship building</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Greeting the patient, using their name, and acknowledging how they feel before diving into
        facts or questions.
      </p>
      <Callout variant="bad" title="Facts first">
        &ldquo;Right, Mr. Patel, I need to ask you about your chest pain.&rdquo; Correct
        information, zero acknowledgement of the person you&rsquo;re talking to.
      </Callout>
      <Callout variant="good" title="Person first">
        &ldquo;Hello Mr. Patel, I understand you&rsquo;ve been having some chest pain &mdash; that
        must be worrying. I&rsquo;d like to ask a few questions so we can look after you
        properly.&rdquo;
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">2. Understanding and incorporating the patient&rsquo;s perspective</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Picking up on what the patient actually says &mdash; a worry, an unexpected detail
        &mdash; rather than delivering your own points regardless of their response.
      </p>
      <Callout variant="bad" title="Ignoring the cue">
        Patient: &ldquo;I&rsquo;m scared it&rsquo;s the same thing that happened to my father.&rdquo;
        Nurse: &ldquo;Okay, so next I&rsquo;ll explain the procedure.&rdquo; The fear is left
        completely unaddressed.
      </Callout>
      <Callout variant="good" title="Responding to the cue">
        &ldquo;I can understand why that would be frightening, given what happened with your
        father. Let&rsquo;s talk through what we know about your situation specifically.&rdquo;
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">3. Providing structure</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Signposting what&rsquo;s coming next, so the patient (and the examiner) can follow where
        the conversation is going.
      </p>
      <Callout variant="bad" title="No signposting">
        Jumping straight from questions into advice with no transition, leaving the patient
        unsure whether the conversation has moved from gathering information to a decision.
      </Callout>
      <Callout variant="good" title="Clear signposting">
        &ldquo;I&rsquo;d like to ask a few questions first, then explain what happens next.&rdquo;
        One sentence, and the whole roleplay becomes easier to follow for everyone.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">4. Information gathering</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Open questions first to let the patient talk, closed questions to confirm specifics, then
        summarising back what you&rsquo;ve heard.
      </p>
      <Callout variant="bad" title="Closed questions only">
        &ldquo;Is the pain sharp? Is it worse at night? Have you taken paracetamol?&rdquo; &mdash;
        efficient, but the patient never gets to say anything you didn&rsquo;t already predict.
      </Callout>
      <Callout variant="good" title="Open, then closed">
        &ldquo;Can you tell me more about the pain?&rdquo; followed by targeted follow-ups once
        the patient has described it in their own words.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">5. Information giving</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Explaining a diagnosis, procedure, or advice in a way the patient can actually follow
        &mdash; as suggestions, not orders &mdash; and checking they&rsquo;ve understood.
      </p>
      <Callout variant="bad" title="Jargon, no check">
        &ldquo;You&rsquo;ll need a course of prophylactic antibiotics post-operatively.&rdquo;
        Technically correct, and the patient has no real idea what that means or whether they
        agree.
      </Callout>
      <Callout variant="good" title="Plain language, checked">
        &ldquo;We&rsquo;ll give you some antibiotics after the surgery to help prevent infection
        &mdash; does that make sense, or would you like me to go over it again?&rdquo;
      </Callout>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-8 mb-2">Linguistic criteria (40% of your band)</h3>

      <p className="text-gray-600 leading-relaxed mb-2 font-semibold text-[#0F2356]">6. Intelligibility</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Pronunciation, word stress, and rhythm clear enough that a listener doesn&rsquo;t have to
        work to understand you &mdash; not the same as having zero accent.
      </p>
      <Callout variant="tip" title="How to improve">
        Record yourself explaining a common procedure and listen back specifically for words you
        rush or swallow &mdash; usually a handful of recurring words, not your speech in general.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">7. Fluency</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Speaking at a natural pace with natural pauses, without long silences or a stream of
        &ldquo;um&rdquo; and &ldquo;ah&rdquo; while you search for words.
      </p>
      <Callout variant="tip" title="How to improve">
        A short thinking pause is completely normal and doesn&rsquo;t cost marks &mdash; it&rsquo;s
        the filler-word habit that fills every pause that examiners notice, since it obscures
        whether you&rsquo;re actually forming a clear thought.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">8. Appropriateness of language</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Register suited to a patient conversation &mdash; professional but plain, with medical
        terms explained rather than assumed.
      </p>
      <Callout variant="bad" title="Wrong register">
        &ldquo;We&rsquo;ll need to cannulate you and start you on IV fluids for your
        hypovolaemia.&rdquo; Correct clinically, unintelligible to most patients.
      </Callout>
      <Callout variant="good" title="Right register">
        &ldquo;We&rsquo;re going to put a small tube into a vein in your arm so we can give you
        fluids directly, since you&rsquo;re a bit dehydrated.&rdquo;
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-2 mt-6 font-semibold text-[#0F2356]">9. Resources of grammar and expression</p>
      <p className="text-gray-600 leading-relaxed mb-3">
        Range and accuracy of grammar and vocabulary under real-time pressure &mdash; varied
        sentence structure, not just correctness.
      </p>
      <Callout variant="tip" title="How to improve">
        Under pressure, most candidates default to short, simple sentences on repeat. Practising
        out loud &mdash; not just reading &mdash; is what builds the reflex to vary structure
        without stopping to think about grammar mid-sentence.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-4 mt-6">
        The clinical communication half is what trips up strong English speakers most often
        &mdash; fluent grammar doesn&apos;t score well if you talk over the patient or forget to
        check they&apos;ve understood.
      </p>

      <LearnCTA
        heading="Practise against all 9 criteria"
        description="SpeakOET's AI patient improvises like a real interlocutor and scores every roleplay against the same 9 criteria above."
        href="/practice/speaking"
        label="Try a Free Roleplay"
      />

      {/* ---------------------------------------------------------- */}
      <h2 id="step-by-step-strategy" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A step-by-step exam strategy
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Speaking doesn&rsquo;t run on a clock you manage minute by minute the way Reading does
        &mdash; but each stage still has a clear job, and most lost marks come from skipping one.
      </p>

      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 pr-4 text-[#0F2356] font-semibold">Stage</th>
              <th className="text-left py-2 text-[#0F2356] font-semibold">What to do</th>
            </tr>
          </thead>
          <tbody className="text-gray-600">
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Reading the card</td>
              <td className="py-2">Identify who you are, who the patient is, what they&rsquo;re likely worried about, and the 2–4 points you must cover. Note key words, not full sentences.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Planning your order</td>
              <td className="py-2">Decide roughly which point comes first, second, third — the card rarely lists them in the ideal spoken order.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Opening</td>
              <td className="py-2">Greet the patient by name and acknowledge their situation before asking or explaining anything.</td>
            </tr>
            <tr className="border-b border-gray-100">
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Middle of the roleplay</td>
              <td className="py-2">Work through your points, but react to whatever the interlocutor actually says — an unexpected question is not a distraction from the task, it is part of it.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 whitespace-nowrap font-semibold text-[#0F2356]">Closing</td>
              <td className="py-2">Check understanding and confirm next steps before the interlocutor ends the roleplay — don&rsquo;t let it just trail off.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 className="text-lg font-semibold text-[#0F2356] mt-6 mb-2">Decision tree: interlocutor says something unexpected?</h3>
      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="mb-2"><span className="font-semibold text-[#0F2356]">Does it directly relate to one of your card&rsquo;s required points?</span></p>
        <p className="mb-2 pl-4">Yes → address it as part of that point, then continue your planned order.</p>
        <p className="pl-4">No → briefly acknowledge it (don&rsquo;t ignore the patient), then bridge back: &ldquo;that&rsquo;s a good question, I&rsquo;ll come back to it — first let me just check…&rdquo;</p>
      </div>

      <Callout variant="warning" title="If you go blank mid-roleplay">
        A short pause to think costs you nothing. What costs you marks is abandoning the
        conversation&rsquo;s structure entirely — take the pause, then return to your next planned
        point rather than improvising something unrelated out of panic.
      </Callout>

      {/* ---------------------------------------------------------- */}
      <h2 id="worked-example" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        A full worked example
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        Here&rsquo;s a realistic (invented) roleplay card, followed by two short excerpts of how
        the same moment can go &mdash; one losing marks, one scoring well &mdash; with the
        reasoning for each.
      </p>

      <div className="rounded-xl border border-gray-100 bg-[#F8FAFC] p-5 mb-4 text-sm text-gray-700 leading-relaxed">
        <p className="font-semibold text-[#0F2356] mb-2">Roleplay card</p>
        <p className="mb-1">Setting: Orthopaedic ward, day 1 after hip replacement surgery.</p>
        <p className="mb-1">Patient: Mrs. Chen, anxious about her first physiotherapy session this afternoon.</p>
        <p className="mb-2">Your tasks:</p>
        <p className="mb-1">— Explain why early mobilisation after hip replacement is recommended</p>
        <p className="mb-1">— Address her fear of falling or the new hip &ldquo;giving way&rdquo;</p>
        <p className="mb-1">— Explain briefly what will happen during the physio session</p>
        <p>— Check she feels ready and confirm next steps</p>
      </div>

      <Callout variant="bad" title="Weak opening — task-first, card followed like a checklist">
        &ldquo;Mrs. Chen, this afternoon you have physiotherapy. It&rsquo;s important to mobilise
        early after hip surgery to prevent complications like blood clots and stiffness. The
        physiotherapist will help you stand and take a few steps.&rdquo; All three facts are
        correct. Nothing has acknowledged that she&rsquo;s frightened, and the tasks were
        delivered as one uninterrupted block rather than a conversation.
      </Callout>
      <Callout variant="good" title="Strong opening — person first, then structure">
        &ldquo;Hello Mrs. Chen, how are you feeling this morning? I know you have physiotherapy
        this afternoon, and I wanted to talk that through with you, since I understand you might
        be feeling a little nervous about it. Is that fair to say?&rdquo; The patient&rsquo;s
        likely emotional state is named before any clinical content, and the sentence ends with a
        genuine question rather than moving straight on.
      </Callout>

      <p className="text-gray-600 leading-relaxed mb-3">
        <span className="font-semibold text-[#0F2356]">Why the strong version scores higher:</span>{' '}
        it hasn&rsquo;t sacrificed any information &mdash; both versions eventually cover the same
        three tasks. The difference is entirely in relationship building and providing structure,
        two of the five clinical communication criteria, which is exactly why two candidates who
        &ldquo;covered everything on the card&rdquo; can still score very differently.
      </p>
      <p className="text-gray-600 leading-relaxed mb-4">
        The same pattern repeats through the rest of the roleplay: when Mrs. Chen says
        &ldquo;I&rsquo;m scared it might just give way while I&rsquo;m walking,&rdquo; a
        card-following response moves straight to explaining the physio session; a strong response
        answers the fear directly first (&ldquo;that&rsquo;s a very common worry, but the new
        joint is designed to bear your weight from day one, and the physiotherapist will be right
        beside you&rdquo;) before continuing. Same information, delivered as a response to the
        patient rather than a script running on schedule.
      </p>

      {/* ---------------------------------------------------------- */}
      <h2 id="common-mistakes" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        18 mistakes that quietly cap your score
      </h2>
      <p className="text-gray-600 leading-relaxed mb-4">
        None of these will make the roleplay collapse &mdash; they just quietly cap a score that
        otherwise sounds fluent and confident.
      </p>
      <ol className="list-decimal pl-5 space-y-3 text-gray-600 mb-4">
        <li><span className="font-semibold text-[#0F2356]">Launching straight into facts without acknowledging the patient first.</span> Costs relationship building before you&rsquo;ve said anything clinically wrong.</li>
        <li><span className="font-semibold text-[#0F2356]">Delivering a memorised script instead of reacting to what the interlocutor says.</span> Examiners can tell within seconds when a candidate is running a rehearsed monologue.</li>
        <li><span className="font-semibold text-[#0F2356]">Using clinical jargon without checking the patient understood.</span> Correct terminology scores nothing if the patient is left confused.</li>
        <li><span className="font-semibold text-[#0F2356]">Missing one of the card&rsquo;s required points under time pressure.</span> Usually caused by poor prep-time planning, not running out of things to say.</li>
        <li><span className="font-semibold text-[#0F2356]">Talking without structure.</span> No signposting means the examiner can&rsquo;t follow where the conversation is going, even if every fact is correct.</li>
        <li><span className="font-semibold text-[#0F2356]">Asking only closed questions.</span> Efficient, but it never lets the patient describe things in their own words — losing information-gathering marks.</li>
        <li><span className="font-semibold text-[#0F2356]">Ignoring an emotional cue.</span> A patient naming a fear or worry that gets no acknowledgement at all before you move on.</li>
        <li><span className="font-semibold text-[#0F2356]">Giving advice as an order rather than a suggestion.</span> &ldquo;You need to do X&rdquo; instead of &ldquo;I&rsquo;d recommend X, how does that sound?&rdquo;</li>
        <li><span className="font-semibold text-[#0F2356]">Never checking understanding.</span> Explaining something once and moving on, with no &ldquo;does that make sense?&rdquo; moment anywhere in the roleplay.</li>
        <li><span className="font-semibold text-[#0F2356]">Filling every pause with &ldquo;um&rdquo; or &ldquo;ah.&rdquo;</span> A brief silent pause to think reads as natural; a constant verbal tic reads as disfluency.</li>
        <li><span className="font-semibold text-[#0F2356]">Rushing to finish within 5 minutes.</span> Speeding through the card to make sure everything gets said, at the cost of intelligibility and structure.</li>
        <li><span className="font-semibold text-[#0F2356]">Treating an unexpected question as an interruption.</span> Deflecting or ignoring it instead of briefly addressing it, which directly costs the patient-perspective criterion.</li>
        <li><span className="font-semibold text-[#0F2356]">Over-preparing one fixed opening line.</span> A line that doesn&rsquo;t fit the specific card still gets used, and it visibly doesn&rsquo;t match the scenario.</li>
        <li><span className="font-semibold text-[#0F2356]">Speaking only in short, simple sentences throughout.</span> Safe, but it caps the resources-of-grammar-and-expression criterion, which rewards range.</li>
        <li><span className="font-semibold text-[#0F2356]">Not using the patient&rsquo;s name.</span> A small detail that repeatedly signals relationship building across the whole conversation.</li>
        <li><span className="font-semibold text-[#0F2356]">Ending abruptly once the last card point is covered.</span> No closing check or confirmation of next steps, so the conversation just stops.</li>
        <li><span className="font-semibold text-[#0F2356]">Practising only with a script, never live improvisation.</span> Builds confidence with memorised lines that collapses the moment a real interlocutor deviates from them.</li>
        <li><span className="font-semibold text-[#0F2356]">Only practising roleplays you find easy.</span> Avoiding scenarios involving bad news, anger, or confusion means the first time you face one for real is in the actual exam.</li>
      </ol>

      {/* ---------------------------------------------------------- */}
      <h2 id="tutor-tips" className="text-2xl font-bold text-[#0F2356] mt-10 mb-4">
        Tips from experienced OET tutors
      </h2>
      <ul className="list-disc pl-5 space-y-3 text-gray-600 mb-4">
        <li>Build a flexible opening &ldquo;shape&rdquo; (greet, name, acknowledge, signpost) rather than a fixed sentence — it adapts to any card instead of sounding rehearsed on the ones it doesn&rsquo;t fit.</li>
        <li>Record every practice roleplay and listen back once for content, once purely for filler words — the two passes catch different problems.</li>
        <li>Practise scenarios you&rsquo;d normally avoid: an angry relative, a patient refusing treatment, delivering unwelcome news. These come up, and the exam is the wrong place to try them for the first time.</li>
        <li>During prep time, write down the patient&rsquo;s likely emotional state in one word before anything else — it forces relationship building to happen early instead of being an afterthought.</li>
        <li>Ask a practice partner (or an AI patient) to genuinely improvise and interrupt, rather than sitting silently while you deliver your card — the improvisation is the actual skill being tested.</li>
        <li>Don&rsquo;t memorise full answers to common scenarios. Memorise structure (open → gather → explain → check) and let the specific words come from the specific card.</li>
        <li>Get feedback against the 9 named criteria specifically, not general impressions — &ldquo;that sounded good&rdquo; from a friend doesn&rsquo;t tell you whether you lost marks on structure or on patient perspective.</li>
        <li>Practise standing up or sitting the way you would in a real consultation, not slouched at a laptop reading notes off-screen — posture and delivery habits carry over into how you sound.</li>
        <li>If a practice roleplay goes badly, redo the exact same card a day later rather than moving straight to a new one. Fixing the specific breakdown matters more than accumulating new scenarios.</li>
      </ul>

      <p className="text-gray-600 leading-relaxed mb-8">
        Always check the exact current format, timing and marking guide on the official OET
        website &mdash; those details are set by OET, not by us.
      </p>

      <FaqSection faqs={faqs} />

      {/* ---------------------------------------------------------- */}
      <h2 id="related-guides" className="text-2xl font-bold text-[#0F2356] mt-12 mb-4">
        Related guides
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 mb-4 text-sm">
        <Link href="/learn/what-is-oet-speaking" className="text-[#0F2356] font-semibold underline">
          What is OET Speaking?
        </Link>
        <Link href="/learn/oet-speaking-tips" className="text-[#0F2356] font-semibold underline">
          OET Speaking Tips for Nurses
        </Link>
        <Link href="/learn/oet-writing" className="text-[#0F2356] font-semibold underline">
          OET Writing Guide for Nurses
        </Link>
        <Link href="/learn/oet-reading" className="text-[#0F2356] font-semibold underline">
          OET Reading Guide for Nurses
        </Link>
        <Link href="/learn/oet-listening" className="text-[#0F2356] font-semibold underline">
          OET Listening Guide for Nurses
        </Link>
        <Link href="/learn/oet-band-scores" className="text-[#0F2356] font-semibold underline">
          OET Band Scores Explained
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
        <Link href="/practice/mock" className="text-[#0F2356] font-semibold underline">
          Full 4-Skill Mock Test
        </Link>
      </div>

      <LearnCTA
        heading="Ready to try a real roleplay?"
        description="Free AI patient roleplay with instant scoring against all 9 official criteria and detailed feedback on exactly what to fix."
        href="/practice/speaking"
        label="Start Free Speaking Practice"
      />
    </main>
  )
}
