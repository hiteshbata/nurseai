// Every claim here must stay literally true — that is the point of this
// section. It asserts: registered nurse, MSc Nursing completed, four years as
// a professor in a nursing college, prepared for OET personally. Do not add
// specifics (hospital names, exam scores, pass claims) that did not happen.
const FOUNDER = {
  heading: 'Built by a Nurse. Designed for Nurses.',
  name: 'Hitesh Bata',
  role: 'Registered Nurse, MSc Nursing · Founder, SpeakOET',
  initials: 'HB',
  story:
    "I'm a registered nurse with an MSc in Nursing, and I spent four years teaching as a professor in a nursing college. When I decided to work abroad, I ran into OET — and found that every coaching class will teach you how to pass each module, but nobody gives you the one thing that actually gets you there: practice. I paid a tutor, hunted for partners on Discord, tried everything I could find. I built SpeakOET so any nurse preparing for OET can just practise, pass, and go build a career anywhere.",
}

export default function FounderSection() {
  return (
    <section className="bg-[#0F2356] py-16 md:py-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center text-center gap-6">
          <div className="w-24 h-24 rounded-full bg-white/10 border border-white/20 flex items-center justify-center shrink-0">
            <span className="text-2xl font-bold text-white/70">{FOUNDER.initials}</span>
          </div>

          <h2 className="text-3xl md:text-4xl font-bold text-white text-balance">{FOUNDER.heading}</h2>

          <p className="text-white/80 text-base leading-relaxed max-w-xl text-balance">{FOUNDER.story}</p>

          <div className="flex flex-col gap-0.5">
            <span className="text-white font-semibold text-sm">{FOUNDER.name}</span>
            <span className="text-white/60 text-xs">{FOUNDER.role}</span>
          </div>
        </div>
      </div>
    </section>
  )
}
