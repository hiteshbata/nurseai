import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'
import { RevealOnScroll } from '@/components/RevealOnScroll'
import { Sparkles, Zap, Clock, TrendingUp, MousePointerClick, Wallet } from 'lucide-react'

export const metadata: Metadata = {
  title: 'About Us',
  description:
    'SpeakOET is an intelligent, automated practice platform helping nurses, doctors, and allied health professionals prepare for the OET exam smarter, faster, and entirely on their own schedule.',
  alternates: { canonical: '/about' },
}

const WHY_CHOOSE = [
  {
    icon: Zap,
    title: 'AI-Powered Practice',
    body: 'Engage in dynamic, lifelike speaking exercises tailored specifically to the healthcare context, allowing you to simulate the real testing environment without needing a live tutor.',
  },
  {
    icon: Sparkles,
    title: 'Instant, Actionable Feedback',
    body: 'Waiting days for a coach to grade your practice is a thing of the past. Receive immediate, detailed evaluations and scoring estimates the moment you finish speaking so you know exactly where to improve.',
  },
  {
    icon: Clock,
    title: 'Study Anytime, Anywhere',
    body: 'Your schedule is unpredictable, so our platform is always on. Whether you have fifteen minutes on a commute or an hour after a night shift, SpeakOET is ready when you are.',
  },
  {
    icon: TrendingUp,
    title: 'Clear Progress Tracking',
    body: 'Motivation comes from seeing real improvement. Our intuitive dashboard automatically logs your practice history, tracks your scores, and highlights your performance trends over time.',
  },
  {
    icon: MousePointerClick,
    title: 'User-Friendly Experience',
    body: "You don't need a manual to use our app. We designed a distraction-free, modern interface that lets you dive straight into learning without fighting with complicated software.",
  },
  {
    icon: Wallet,
    title: 'Affordable Preparation',
    body: 'Gain access to premium-quality practice tools and continuous feedback at a fraction of the cost of traditional, hourly coaching.',
  },
]

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Hero */}
      <div className="max-w-3xl mx-auto px-4 pt-20 pb-14 text-center motion-safe:animate-[fade-up-in_0.6s_ease-out_both]">
        <h1 className="font-display text-4xl md:text-6xl font-semibold text-[#0F2356] text-balance leading-[1.05]">
          Empowering healthcare professionals to speak with confidence
        </h1>
        <p className="text-gray-500 mt-5 text-lg leading-relaxed text-balance">
          SpeakOET is an intelligent, automated practice platform designed to help medical
          professionals prepare for the OET exam smarter, faster, and entirely on their own
          schedule.
        </p>
      </div>

      <div className="max-w-3xl mx-auto px-4 pb-24">
        <RevealOnScroll className="mb-16">
          <section aria-labelledby="who-we-are">
            <h2 id="who-we-are" className="font-display text-2xl font-semibold text-[#0F2356] mb-4">
              Who We Are
            </h2>
            <p className="text-gray-600 leading-relaxed mb-4">
              As a healthcare professional, your time is your most valuable resource. Balancing long
              shifts, demanding patient care, and a personal life leaves little room for rigid,
              scheduled tutoring sessions. That is exactly why we built SpeakOET.
            </p>
            <p className="text-gray-600 leading-relaxed mb-4">
              SpeakOET is a specialized educational platform designed exclusively for nurses, doctors,
              and allied health professionals preparing for the Occupational English Test (OET). We
              understand that the OET is more than just a language exam — it is a critical stepping
              stone to international career opportunities, professional growth, and global mobility.
            </p>
            <p className="text-gray-600 leading-relaxed">
              To help you get there, our platform provides a modern, intuitive space where you can
              practice your English speaking skills in realistic healthcare scenarios, completely on
              your own terms. We have combined user-friendly design with modern learning tools to
              create a study companion that understands the unique demands of a medical career.
            </p>
          </section>
        </RevealOnScroll>

        <RevealOnScroll className="mb-16">
          <section aria-labelledby="our-mission">
            <h2 id="our-mission" className="font-display text-2xl font-semibold text-[#0F2356] mb-4">
              Our Mission
            </h2>
            <p className="text-gray-600 leading-relaxed mb-4">
              Our mission is straightforward: we want to make OET preparation more accessible,
              affordable, and highly effective for medical professionals around the world.
            </p>
            <p className="text-gray-600 leading-relaxed mb-4">
              Historically, high-quality OET coaching has been expensive and difficult to fit into a
              working healthcare provider&apos;s schedule. We created SpeakOET to disrupt this
              outdated model. By bringing intelligent, responsive practice directly to your
              fingertips, we aim to remove the stress and financial burden of exam preparation.
            </p>
            <p className="text-gray-600 leading-relaxed">
              We believe that every skilled healthcare worker deserves access to top-tier learning
              tools that adapt to their busy lives. Our goal is to empower you to walk into the exam
              room feeling fully prepared, highly capable, and undeniably confident.
            </p>
          </section>
        </RevealOnScroll>

        <RevealOnScroll className="mb-16">
          <section aria-labelledby="why-choose">
            <h2 id="why-choose" className="font-display text-2xl font-semibold text-[#0F2356] mb-3">
              Why Choose SpeakOET
            </h2>
            <p className="text-gray-600 leading-relaxed mb-8">
              We know you have options when it comes to studying. SpeakOET is thoughtfully crafted to
              focus on what actually drives results, stripping away the noise to give you a clean,
              focused learning experience. Here is why professionals trust us as their study partner:
            </p>
            <div className="grid sm:grid-cols-2 gap-5">
              {WHY_CHOOSE.map(({ icon: Icon, title, body }) => (
                <div
                  key={title}
                  className="rounded-2xl border border-gray-200 p-6 shadow-premium hover:-translate-y-0.5 hover:shadow-premium-lg transition-all duration-200"
                >
                  <Icon className="w-5 h-5 text-[#047857] mb-3" strokeWidth={1.75} aria-hidden="true" />
                  <p className="font-semibold text-[#0F2356] mb-1.5">{title}</p>
                  <p className="text-sm text-gray-600 leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </section>
        </RevealOnScroll>

        <RevealOnScroll className="mb-16">
          <section aria-labelledby="our-vision">
            <h2 id="our-vision" className="font-display text-2xl font-semibold text-[#0F2356] mb-4">
              Our Vision
            </h2>
            <p className="text-gray-600 leading-relaxed mb-4">
              We look toward a future where language barriers never prevent talented healthcare
              professionals from achieving their ultimate career aspirations. The world needs skilled
              medical staff, and we are committed to smoothing the pathway for those who wish to work
              globally.
            </p>
            <p className="text-gray-600 leading-relaxed">
              By continually refining our tools and providing smarter, more accessible exam
              preparation, we envision SpeakOET as the global standard for language practice in the
              medical field. We want to help you cross borders, seize international opportunities,
              and deliver exceptional care in English-speaking environments worldwide.
            </p>
          </section>
        </RevealOnScroll>

        <RevealOnScroll>
          <section aria-labelledby="ready">
            <h2 id="ready" className="font-display text-2xl font-semibold text-[#0F2356] mb-4">
              Ready to Transform Your Preparation?
            </h2>
            <p className="text-gray-600 leading-relaxed">
              Your next career milestone is within reach, and consistent, targeted practice is the
              key to unlocking it. Don&apos;t leave your OET performance to chance. Join the growing
              community of healthcare professionals who are taking control of their study routines
              with SpeakOET. Start building your confidence, improving your fluency, and tracking your
              success today.
            </p>
          </section>
        </RevealOnScroll>

        <LearnCTA />
      </div>
    </main>
  )
}
