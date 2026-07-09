import Link from 'next/link'

export function LearnCTA() {
  return (
    <div className="mt-12 rounded-2xl border border-gray-100 bg-[#F8FAFC] p-8 text-center">
      <h3 className="text-xl font-bold text-[#0F2356] mb-2">Ready to practice?</h3>
      <p className="text-gray-500 mb-5">
        Roleplay with an AI patient and get instant 9-criteria feedback on your OET Speaking.
      </p>
      <Link
        href="/auth/register"
        className="inline-flex items-center justify-center bg-[#10B981] text-white font-semibold px-6 py-3 rounded-lg hover:bg-[#0ea472] transition-colors"
      >
        Start Free Practice
      </Link>
    </div>
  )
}
