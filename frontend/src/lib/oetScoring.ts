// Mirrors backend/app/services/ai_scoring.py _writing_grade -- OET publishes
// one A-E grade scale (0-500) shared by all four sub-tests, not just Writing.
// Update both places together if OET revises the published boundaries.
export type OetGrade = 'A' | 'B' | 'C+' | 'C' | 'D' | 'E'

const GRADE_FLOORS: [OetGrade, number][] = [
  ['A', 450],
  ['B', 350],
  ['C+', 300],
  ['C', 200],
  ['D', 100],
  ['E', 0],
]

export const GRADE_ORDER: OetGrade[] = ['E', 'D', 'C', 'C+', 'B', 'A']

export function scoreToGrade(score: number): OetGrade {
  for (const [grade, floor] of GRADE_FLOORS) {
    if (score >= floor) return grade
  }
  return 'E'
}

export function gradeToFloorScore(grade: OetGrade): number {
  return GRADE_FLOORS.find(([g]) => g === grade)![1]
}

export type PassStatus = 'pass' | 'fail' | 'borderline'

// Numeric mode: exact comparison. Grade-only mode: a grade is a band (e.g. B
// spans 350-440), so when the requirement doesn't sit exactly on a band floor
// (Ahpra's 360 for Reading/Speaking) a grade alone can't prove pass or fail --
// report "borderline" and ask for the exact number rather than guess.
export function compareToRequirement(
  userValue: { mode: 'number'; score: number } | { mode: 'grade'; grade: OetGrade },
  required: number
): PassStatus {
  if (userValue.mode === 'number') {
    return userValue.score >= required ? 'pass' : 'fail'
  }
  const requiredGrade = scoreToGrade(required)
  const userRank = GRADE_ORDER.indexOf(userValue.grade)
  const reqRank = GRADE_ORDER.indexOf(requiredGrade)
  if (userRank > reqRank) return 'pass'
  if (userRank < reqRank) return 'fail'
  return required === gradeToFloorScore(requiredGrade) ? 'pass' : 'borderline'
}

export type OetModule = 'listening' | 'reading' | 'writing' | 'speaking'

export const MODULE_LABELS: Record<OetModule, string> = {
  listening: 'Listening',
  reading: 'Reading',
  writing: 'Writing',
  speaking: 'Speaking',
}

export interface Regulator {
  id: string
  name: string
  country: string
  sourceLabel: string
  sourceUrl: string
  requirements: Record<OetModule, number>
  note?: string
}

const OET_DIRECTORY = 'https://oet.com/test/who-recognises-oet/recognising-organisations'

// Sourced directly from oet.com's own "Who accepts your OET Test scores"
// directory per country (the recognising-organisations pages), cross-checked
// against each regulator's own site where that loaded. Regulators change
// these numbers over time; this is a study aid, not a guarantee, and the
// page says so next to every result. Deliberately excluded rather than
// guessed: UAE (DHA/DOH/MOH) -- sources conflicted and requirements aren't
// uniform across emirates; Singapore (SNB) and Malta (CNM) -- no oet.com
// directory data pulled for them yet, only secondary sources, not good
// enough to publish a pass/fail claim against.
export const REGULATORS: Regulator[] = [
  {
    id: 'nmc',
    name: 'NMC',
    country: 'United Kingdom',
    sourceLabel: "NMC — accepted English language tests",
    sourceUrl:
      'https://www.nmc.org.uk/registration/joining-the-register/english-language-requirements/accepted-english-language-tests/',
    requirements: { listening: 350, reading: 350, writing: 300, speaking: 350 },
  },
  {
    id: 'ahpra',
    name: 'Ahpra / NMBA',
    country: 'Australia',
    sourceLabel: 'OET — Who accepts your OET Test scores in Australia (Ahpra, ANMAC)',
    sourceUrl: `${OET_DIRECTORY}/australia`,
    requirements: { listening: 350, reading: 350, writing: 350, speaking: 350 },
  },
  {
    id: 'nmbi',
    name: 'NMBI',
    country: 'Ireland',
    sourceLabel: 'OET — Who accepts your OET Test scores in Ireland (NMBI)',
    sourceUrl: `${OET_DIRECTORY}/ireland`,
    requirements: { listening: 350, reading: 350, writing: 350, speaking: 350 },
  },
  {
    id: 'nz',
    name: 'Nursing Council',
    country: 'New Zealand',
    sourceLabel: 'OET — Who accepts your OET Test scores in New Zealand (Nursing Council)',
    sourceUrl: `${OET_DIRECTORY}/new-zealand`,
    requirements: { listening: 350, reading: 350, writing: 300, speaking: 350 },
  },
  {
    id: 'canada',
    name: 'Provincial/territorial nursing regulators',
    country: 'Canada',
    sourceLabel: 'OET — Who accepts your OET Test scores in Canada (13 provincial/territorial nursing regulators)',
    sourceUrl: `${OET_DIRECTORY}/canada`,
    requirements: { listening: 350, reading: 300, writing: 300, speaking: 350 },
    note: 'Confirmed identical across every provincial and territorial RN/LPN regulator listed by OET (Ontario, BC, Alberta, Manitoba, Saskatchewan, Nova Scotia, New Brunswick, PEI, Newfoundland & Labrador, NWT/Nunavut, Yukon) — not a single-province guess.',
  },
  {
    id: 'us-trumerit',
    name: 'TruMerit / CGFNS (national credentialing)',
    country: 'United States',
    sourceLabel: 'OET — Who accepts your OET Test scores in the USA (TruMerit)',
    sourceUrl: `${OET_DIRECTORY}/united-states`,
    requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 },
    note: 'The credential-verification pathway most US-bound nurses go through regardless of state — use this if your state board isn’t listed below.',
  },
  { id: 'us-al', name: 'Alabama Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Alabama)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-ak', name: 'Alaska Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Alaska)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-ar', name: 'Arkansas State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Arkansas)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-ct', name: 'Connecticut Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Connecticut)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-de', name: 'Delaware Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Delaware)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-dc', name: 'District of Columbia Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (District of Columbia)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-fl', name: 'Florida Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Florida)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-hi', name: 'Hawaii Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Hawaii)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-id', name: 'Idaho Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Idaho)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-il', name: 'Illinois Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Illinois)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 200, reading: 200, writing: 200, speaking: 300 } },
  { id: 'us-ia', name: 'Iowa Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Iowa)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-ky', name: 'Kentucky Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Kentucky)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-mi', name: 'Michigan LARA Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Michigan)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-md', name: 'Maryland State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Maryland)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-ma', name: 'Massachusetts Board of Registration in Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Massachusetts)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-ms', name: 'Mississippi Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Mississippi)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-mo', name: 'Missouri State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Missouri)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-ne', name: 'Nebraska Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Nebraska)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-nh', name: 'New Hampshire Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (New Hampshire)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-nj', name: 'New Jersey Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (New Jersey)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-nm', name: 'New Mexico Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (New Mexico)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-nd', name: 'North Dakota Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (North Dakota)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-or', name: 'Oregon State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Oregon)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-sc', name: 'South Carolina Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (South Carolina)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 350, reading: 350, writing: 350, speaking: 350 } },
  { id: 'us-sd', name: 'South Dakota State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (South Dakota)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-tn', name: 'Tennessee Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Tennessee)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-tx', name: 'Texas Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Texas)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
  { id: 'us-ut', name: 'Utah State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Utah)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-vt', name: 'Vermont State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Vermont)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-va', name: 'Virginia Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Virginia)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-wa', name: 'Washington State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Washington)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 200 } },
  { id: 'us-wv', name: 'West Virginia RN Board', country: 'United States', sourceLabel: 'OET — USA directory (West Virginia)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-wi', name: 'Wisconsin Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Wisconsin)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 350 } },
  { id: 'us-wy', name: 'Wyoming State Board of Nursing', country: 'United States', sourceLabel: 'OET — USA directory (Wyoming)', sourceUrl: `${OET_DIRECTORY}/united-states`, requirements: { listening: 300, reading: 300, writing: 300, speaking: 300 } },
]

// States/territories whose OET requirement isn't listed above -- either the
// source said "contact organisation for required score" (Louisiana,
// Minnesota, Pennsylvania) or they simply don't appear in OET's directory.
// Surfaced in the FAQ so the gap is explicit rather than silently missing.
export const US_STATES_NOT_LISTED =
  'Louisiana, Minnesota, and Pennsylvania publish no score on OET’s directory (contact the board directly); other states not listed here may not appear in OET’s directory at all -- use TruMerit/CGFNS as a baseline or check your board directly.'

export interface StudyStep {
  title: string
  body: string
}

// Deterministic, no AI call -- generic OET prep advice per weakest module.
// Not personalized beyond "which sub-test is furthest below target," which is
// exactly the signal an anonymous, un-authenticated visitor can give us.
export const FOUR_WEEK_PLANS: Record<OetModule, StudyStep[]> = {
  listening: [
    { title: 'Week 1', body: 'Learn the format of Parts A, B, and C, and practise note-taking speed on Part A consultation extracts.' },
    { title: 'Week 2', body: 'Drill Part B and C question types (short answer, multiple choice) under real time pressure, one full sub-test per sitting.' },
    { title: 'Week 3', body: 'Review every wrong answer to find your pattern — missed detail, mishearing numbers, or losing focus on longer extracts.' },
    { title: 'Week 4', body: 'Full timed mock Listening sub-test, then a final pass focused only on your weakest part.' },
  ],
  reading: [
    { title: 'Week 1', body: 'Learn the format of Parts A, B, and C, and practise skimming Part A for numbers, dosages, and key terms fast.' },
    { title: 'Week 2', body: 'Time-box Part B and C — these punish slow readers most — and build a habit of answering from evidence, not memory.' },
    { title: 'Week 3', body: 'Build healthcare vocabulary from the specific texts you get wrong; most Reading loss is vocabulary, not comprehension.' },
    { title: 'Week 4', body: 'Full timed mock Reading sub-test, then review pacing across all three parts.' },
  ],
  writing: [
    { title: 'Week 1', body: 'Learn the 6 OET Writing criteria and study 2-3 sample Grade A/B letters against the mark scheme.' },
    { title: 'Week 2', body: 'Practise case-note selection — the single biggest score-killer is including irrelevant information from the notes.' },
    { title: 'Week 3', body: 'Write full letters under 45-minute time pressure and get them scored against the real rubric, not a generic checklist.' },
    { title: 'Week 4', body: 'Focus revision on your lowest-scoring criterion from Week 3, then one final timed letter.' },
  ],
  speaking: [
    { title: 'Week 1', body: 'Learn the 9 OET Speaking criteria and what examiners listen for in the warm-up and each role-play.' },
    { title: 'Week 2', body: 'Practise role-plays out loud daily — Speaking is a performance skill, reading about it doesn’t move the score.' },
    { title: 'Week 3', body: 'Record yourself and compare against the criteria: empathy, structure, and information-gathering are the most commonly missed.' },
    { title: 'Week 4', body: 'Full timed mock role-plays back to back, simulating real exam fatigue.' },
  ],
}
