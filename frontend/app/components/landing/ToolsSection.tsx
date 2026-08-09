import { Calculator, Sparkles, Rocket, ArrowRight } from 'lucide-react'

const TOOLS = [
  {
    href: '/tools/oet-score-calculator',
    icon: Calculator,
    title: 'Score Calculator',
    text: 'Check your OET scores against 30+ nursing regulators worldwide.',
  },
  {
    href: '/tools/ai-study-plan-generator',
    icon: Sparkles,
    title: 'AI Study Plan Generator',
    text: 'Enter your scores and exam date, get a week-by-week plan.',
  },
  {
    href: '/tools/oet-mock-test-free',
    icon: Rocket,
    title: 'Free Mock Test',
    text: 'One full attempt across all four sub-tests, no account needed.',
  },
]

export default function ToolsSection() {
  return (
    <section className="bg-[#F8FAFC] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-[#0F2356] text-balance">
            Free Tools, No Sign-Up Needed
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-0 divide-y md:divide-y-0 md:divide-x divide-gray-200 rounded-2xl border border-gray-200 bg-white shadow-premium overflow-hidden">
          {TOOLS.map(({ href, icon: Icon, title, text }) => (
            <a
              key={title}
              href={href}
              className="group flex flex-col p-8 hover:bg-[#F8FAFC] transition-colors"
            >
              <Icon className="w-6 h-6 text-[#047857] mb-4" strokeWidth={1.75} aria-hidden="true" />
              <h3 className="text-base font-bold text-[#0F2356] mb-1.5">{title}</h3>
              <p className="text-gray-500 text-sm leading-relaxed mb-4 flex-1">{text}</p>
              <span className="inline-flex items-center gap-1 text-sm font-semibold text-[#0F2356] group-hover:gap-2 transition-all">
                Try it free
                <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
