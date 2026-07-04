export default function CTASection() {
  return (
    <section className="bg-[#10B981] py-16 md:py-24">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-4xl md:text-5xl font-bold text-white mb-4 text-balance">Start with 5 Free Sessions</h2>
        <p className="text-white/80 text-lg mb-8 leading-relaxed">
          No credit card. No app download. Open, speak, and get scored in minutes.
        </p>
        <a
          href="/auth/register"
          className="inline-flex items-center bg-white text-[#10B981] font-bold px-8 py-4 rounded-lg text-lg hover:bg-gray-50 transition-colors shadow-lg"
        >
          Start Practicing Free — No Card Needed →
        </a>
        <p className="text-white/70 text-sm mt-5">5 free sessions. Cancel anytime. Takes 2 minutes to set up.</p>
      </div>
    </section>
  )
}
