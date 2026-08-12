import Link from 'next/link'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { TECHNIQUE_PRACTICE_LEARNER_ENABLED } from './config'

function ComingSoon() {
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 flex items-center justify-center">
      <Card className="max-w-lg w-full p-8 text-center">
        <h1 className="text-3xl font-bold text-[#0F2356]">Technique Practice</h1>
        <span className="mt-3 inline-flex items-center rounded-full bg-amber-50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-amber-700">
          Coming Soon
        </span>
        <p className="text-gray-600 mt-4">
          We&apos;re building a more powerful way to help you actually learn and practice OET techniques.
        </p>
        <p className="text-gray-500 mt-3 text-sm">
          Instead of simply answering questions, you&apos;ll soon be able to learn each technique through:
        </p>
        <ul className="mt-4 space-y-2 text-sm text-gray-700 text-left max-w-xs mx-auto">
          <li>🎥 Video learning</li>
          <li>🎯 Guided practice</li>
          <li>⏱️ Timed exercises</li>
          <li>🧠 Personalized feedback</li>
        </ul>
        <Link href="/dashboard">
          <Button className="mt-8 w-full">Continue OET Practice</Button>
        </Link>
      </Card>
    </div>
  )
}

// Gates the entire /practice/technique/* route family (catalog + every
// [slug] page, current and future) behind one flag, without touching the
// Phase C/D pages, API, or data underneath.
export default function TechniquePracticeLayout({ children }: { children: React.ReactNode }) {
  if (!TECHNIQUE_PRACTICE_LEARNER_ENABLED) return <ComingSoon />
  return <>{children}</>
}
