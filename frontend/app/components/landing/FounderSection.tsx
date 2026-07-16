// TODO(founder): fill in FOUNDER before launch — every field here is a
// placeholder.
//
// The heading "Built by a Nurse. Designed for Nurses." is itself a factual
// claim about who built SpeakOET. If the founder is not a nurse, change the
// heading (e.g. "Built for Nurses, With Nurses") rather than shipping it —
// the point of this section is that nothing on this page is fabricated.
const FOUNDER = {
  heading: 'Built by a Nurse. Designed for Nurses.',
  name: 'Founder name',
  role: 'Founder, SpeakOET',
  initials: 'SO',
  story:
    'TODO: your story goes here. Why you built SpeakOET, what you saw nurses struggle with, and why OET Speaking specifically. Two or three sentences is enough — write it in your own voice.',
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
