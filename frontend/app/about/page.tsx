import type { Metadata } from 'next'
import { LearnCTA } from '@/components/learn/LearnCTA'

export const metadata: Metadata = {
  title: 'About Us',
  description:
    'SpeakOET is an intelligent, automated practice platform helping nurses, doctors, and allied health professionals prepare for the OET exam smarter, faster, and entirely on their own schedule.',
}

export default function AboutPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">About Us</h1>
      <p className="text-gray-500 text-lg mb-10">
        Empowering healthcare professionals to speak with confidence. SpeakOET is an intelligent,
        automated practice platform designed to help medical professionals prepare for the OET
        exam smarter, faster, and entirely on their own schedule.
      </p>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Who We Are</h2>
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

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Our Mission</h2>
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

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Why Choose SpeakOET</h2>
        <p className="text-gray-600 leading-relaxed mb-4">
          We know you have options when it comes to studying. SpeakOET is thoughtfully crafted to
          focus on what actually drives results, stripping away the noise to give you a clean,
          focused learning experience. Here is why professionals trust us as their study partner:
        </p>
        <ul className="space-y-4">
          <li>
            <p className="font-semibold text-[#0F2356]">AI-Powered Practice</p>
            <p className="text-gray-600">
              Engage in dynamic, lifelike speaking exercises tailored specifically to the
              healthcare context, allowing you to simulate the real testing environment without
              needing a live tutor.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">Instant, Actionable Feedback</p>
            <p className="text-gray-600">
              Waiting days for a coach to grade your practice is a thing of the past. Receive
              immediate, detailed evaluations and scoring estimates the moment you finish
              speaking so you know exactly where to improve.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">Study Anytime, Anywhere</p>
            <p className="text-gray-600">
              Your schedule is unpredictable, so our platform is always on. Whether you have
              fifteen minutes on a commute or an hour after a night shift, SpeakOET is ready when
              you are.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">Clear Progress Tracking</p>
            <p className="text-gray-600">
              Motivation comes from seeing real improvement. Our intuitive dashboard automatically
              logs your practice history, tracks your scores, and highlights your performance
              trends over time.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">User-Friendly Experience</p>
            <p className="text-gray-600">
              You don&apos;t need a manual to use our app. We designed a distraction-free, modern
              interface that lets you dive straight into learning without fighting with
              complicated software.
            </p>
          </li>
          <li>
            <p className="font-semibold text-[#0F2356]">Affordable Preparation</p>
            <p className="text-gray-600">
              Gain access to premium-quality practice tools and continuous feedback at a fraction
              of the cost of traditional, hourly coaching.
            </p>
          </li>
        </ul>
      </section>

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">Our Vision</h2>
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

      <section className="mb-10">
        <h2 className="text-xl font-bold text-[#0F2356] mb-3">
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

      <LearnCTA />
    </main>
  )
}
