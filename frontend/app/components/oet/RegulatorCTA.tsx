import Link from 'next/link'

const CHECKLIST = ['Free AI Speaking Practice', 'Instant score estimates', 'Real OET roleplays']

export function RegulatorCTA({ regulatorName }: { regulatorName: string }) {
  return (
    <div className="mt-12 rounded-2xl border border-gray-100 bg-[#F8FAFC] p-8 text-center">
      <h3 className="text-xl font-bold text-[#0F2356] mb-4">Ready to achieve the {regulatorName}?</h3>
      <ul className="mb-5 inline-flex flex-col items-start gap-1 text-left text-gray-600">
        {CHECKLIST.map((item) => (
          <li key={item}>
            <span className="text-[#10B981] font-bold">✓</span> {item}
          </li>
        ))}
      </ul>
      <div>
        <Link
          href="/auth/register"
          className="inline-flex items-center justify-center bg-[#10B981] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#0ea472] transition-colors"
        >
          Start Free Practice
        </Link>
      </div>
    </div>
  )
}
