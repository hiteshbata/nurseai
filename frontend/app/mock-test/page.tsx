'use client'

// ponytail: full mock test (timed OET speaking sub-test simulation) not built yet —
// the old page was an MCQ shell over role_play questions with no options/answers,
// so it could never be completed. Honest placeholder until the real feature ships.
import Link from 'next/link'

export default function MockTestPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4 py-12">
      <div className="max-w-md rounded-2xl bg-white p-8 text-center shadow">
        <h1 className="text-3xl font-bold text-[#0F2356]">Mock Test</h1>
        <p className="mt-3 text-gray-600">
          Full timed mock tests are coming soon. Until then, speaking scenarios
          give you the same 9-criteria examiner scoring on every session.
        </p>
        <Link
          href="/practice/speaking"
          className="mt-6 inline-flex items-center justify-center rounded-xl bg-[#0F2356] px-6 py-3 font-semibold text-white hover:bg-[#0F2356]/90 transition"
        >
          Practice Speaking Instead
        </Link>
      </div>
    </div>
  )
}
