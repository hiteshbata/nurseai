'use client'

import Image from 'next/image'
import { useInView } from '@/app/hooks/useInView'

// Every claim here must stay literally true — that is the point of this
// section. It asserts: registered nurse in India, MSc Nursing completed, four
// years as a professor in a nursing college, prepared for OET personally. Do
// not add specifics (hospital names, exam scores, pass claims) that did not
// happen.
//
// "(India)" is load-bearing, not a detail: this page is read by nurses heading
// to Australia, the UK, and New Zealand, so an unqualified "Registered Nurse"
// would imply registration with AHPRA/NMC/NCNZ. Name the country.
const FOUNDER = {
  heading: 'Built by a Nurse. Designed for Nurses.',
  name: 'Hitesh Bata',
  role: 'Registered Nurse (India), MSc Nursing · Founder, SpeakOET',
  photo: '/founder.jpg',
  story:
    "I'm a registered nurse with an MSc in Nursing, and I spent four years teaching as a professor in a nursing college. When I decided to work abroad, I ran into OET. Many coaching classes explain the exam format and strategies, but I found it difficult to get enough realistic speaking practice — I paid a tutor, hunted for partners on Discord, tried everything I could find. I built SpeakOET to help nurses practise OET Speaking consistently, with realistic AI patients and structured feedback.",
}

export default function FounderSection() {
  const { ref, inView } = useInView<HTMLDivElement>()

  return (
    <section className="bg-[#0F2356] py-16 md:py-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div
          ref={ref}
          className="flex flex-col items-center text-center gap-6 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? "translateY(0)" : "translateY(12px)",
          }}
        >
          {/* The source is a 2:3 portrait, so a plain square crop would centre on
              the chest. object-position pulls the crop up to the face; the slight
              zoom fills the circle with head-and-shoulders instead of a distant
              bust — cheaper than shipping a second, pre-cropped copy. */}
          <div className="w-32 h-32 rounded-full overflow-hidden border border-white/20 bg-white/10 shrink-0">
            <Image
              src={FOUNDER.photo}
              alt={`${FOUNDER.name}, founder of SpeakOET`}
              width={256}
              height={384}
              className="w-full h-full object-cover object-[50%_22%] scale-[1.3] origin-[50%_22%]"
            />
          </div>

          <h2 className="font-display text-3xl md:text-4xl font-semibold text-white text-balance">{FOUNDER.heading}</h2>

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
