const testimonials = [
  {
    quote:
      "The AI patient interrupted me every time I said 'hypertension' or 'myocardial'. It was frustrating at first but I learned to speak simply. My Appropriateness score went from C to B.",
    initials: "PM",
    name: "Priya M.",
    location: "Kerala → Australia",
    verified: true,
    bandFrom: "C",
    bandTo: "B",
  },
  {
    quote:
      "I practiced every day for 3 weeks. The AI scenarios felt exactly like what I faced in the real exam. I finally got the B grade I needed.",
    initials: "AR",
    name: "Anitha R.",
    location: "Tamil Nadu → UK",
    verified: true,
    bandFrom: "C+",
    bandTo: "B",
  },
  {
    quote:
      "My coaching centre started using SpeakOET for homework. All 8 students in my batch improved by at least one band grade within a month.",
    initials: "SK",
    name: "Sunita K.",
    location: "Maharashtra → New Zealand",
    verified: true,
    bandFrom: "C",
    bandTo: "B+",
  },
]

export default function TestimonialsSection() {
  return (
    <section className="bg-[#0F2356] py-16 md:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12 text-balance">
          Indian Nurses Who Improved Their OET Band
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map(({ quote, initials, name, location, verified, bandFrom, bandTo }) => (
            <div key={name} className="bg-white/10 rounded-2xl p-7 flex flex-col gap-4">
              {/* Stars */}
              <div className="flex gap-1" role="img" aria-label="5 stars">
                {Array.from({ length: 5 }).map((_, i) => (
                  <svg key={i} className="w-4 h-4 text-yellow-400 fill-yellow-400" viewBox="0 0 20 20" aria-hidden="true">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                ))}
              </div>

              <p className="text-white/80 text-sm leading-relaxed flex-1">&ldquo;{quote}&rdquo;</p>

              <div className="flex items-center gap-3 mt-2">
                <div className="w-10 h-10 rounded-full bg-[#047857] flex items-center justify-center text-white font-bold text-sm shrink-0">
                  {initials}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-white font-semibold text-sm">{name}</span>
                    <span className="bg-[#10B981]/20 text-emerald-300 text-[10px] font-semibold px-1.5 py-0.5 rounded-full border border-[#10B981]/30">
                      Verified Student
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-white/50 text-xs">{location}</span>
                    <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                      {bandFrom} → {bandTo}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
