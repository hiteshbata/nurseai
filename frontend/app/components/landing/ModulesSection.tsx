import { Mic, BookOpen, PenLine, Headphones, ClipboardCheck, ArrowRight } from 'lucide-react'

// Icons match AppShell's NavLinks exactly (Mic/PenLine/BookOpen/Headphones/
// ClipboardCheck) so a signed-up user recognizes the same module by the same
// glyph the moment they land in the app.
const MODULES = [
  {
    icon: BookOpen,
    title: 'Reading',
    text: 'Part A, B and C practice, timed to the real exam format.',
  },
  {
    icon: PenLine,
    title: 'Writing',
    text: 'Referral and discharge letters, scored against the 6-criteria rubric.',
  },
  {
    icon: Headphones,
    title: 'Listening',
    text: 'Three-part audio practice, played once, just like exam day.',
  },
  {
    icon: ClipboardCheck,
    title: 'Mock Test',
    text: 'All four sub-tests in one sitting, with a full band report.',
    tint: true,
  },
]

export default function ModulesSection() {
  return (
    <section className="bg-white py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-[#0F2356] text-balance">
            One Platform, Every OET Sub-Test
          </h2>
          <p className="text-gray-500 text-lg mt-3 max-w-xl mx-auto text-balance">
            Speaking, Reading, Writing, Listening and full Mock Tests, all scored by the same AI engine.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 lg:grid-rows-2 gap-4 lg:h-[420px]">
          {/* Speaking — the differentiator, given the full 2x2 block */}
          <a
            href="/auth/register"
            className="group lg:col-span-2 lg:row-span-2 rounded-2xl bg-[#0F2356] p-8 flex flex-col justify-between shadow-premium-lg hover:shadow-premium transition-shadow"
          >
            <div>
              <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center mb-6">
                <Mic className="w-6 h-6 text-[#10B981]" strokeWidth={1.75} aria-hidden="true" />
              </div>
              <h3 className="font-display text-2xl font-semibold text-white mb-2">Speaking</h3>
              <p className="text-white/70 leading-relaxed max-w-sm">
                Roleplay with an AI patient that responds in real time and scores all 9 OET criteria.
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#10B981] group-hover:gap-2.5 transition-all">
              Try Speaking practice
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </span>
          </a>

          {MODULES.map(({ icon: Icon, title, text, tint }) => (
            <a
              key={title}
              href="/auth/register"
              className={`group rounded-2xl p-6 flex flex-col justify-between border transition-colors ${
                tint
                  ? 'bg-emerald-50 border-emerald-200 hover:border-emerald-300'
                  : 'bg-white border-gray-100 hover:border-gray-200 shadow-premium'
              }`}
            >
              <div>
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${
                    tint ? 'bg-emerald-100' : 'bg-[#0F2356]/5'
                  }`}
                >
                  <Icon
                    className={`w-5 h-5 ${tint ? 'text-[#047857]' : 'text-[#0F2356]'}`}
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                </div>
                <h3 className="text-base font-bold text-[#0F2356] mb-1.5">{title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed">{text}</p>
              </div>
              <span
                className={`inline-flex items-center gap-1 text-xs font-semibold mt-4 group-hover:gap-2 transition-all ${
                  tint ? 'text-[#047857]' : 'text-[#0F2356]'
                }`}
              >
                Explore
                <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
