import { RevealOnScroll } from '@/components/RevealOnScroll'

const MISTAKES = [
  'Assume old score requirements still apply.',
  "Forget to check the regulator's latest English-language policy.",
  'Submit an OET result outside the accepted validity period.',
  'Misunderstand whether two sittings can be combined.',
]

export function CommonMistakes() {
  return (
    <RevealOnScroll>
      <h2 className="font-display text-xl font-semibold text-[#0F2356] mt-8 mb-3">Common mistakes</h2>
      <p className="text-gray-600 leading-relaxed mb-3">
        Many candidates delay registration because they:
      </p>
      <ul className="list-disc pl-5 space-y-2 text-gray-600 mb-4">
        {MISTAKES.map((mistake) => (
          <li key={mistake}>{mistake}</li>
        ))}
      </ul>
    </RevealOnScroll>
  )
}
