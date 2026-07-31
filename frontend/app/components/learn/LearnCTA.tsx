import Link from 'next/link'

export function LearnCTA({
  heading = 'Ready to practice?',
  description = 'Roleplay with an AI patient and get instant 9-criteria feedback on your OET Speaking.',
  href = '/auth/register',
  label = 'Start Free Practice',
}: {
  heading?: string
  description?: string
  href?: string
  label?: string
}) {
  return (
    <div className="mt-12 rounded-3xl bg-[#0F2356] px-8 py-12 text-center shadow-premium">
      <h3 className="font-display text-2xl font-semibold text-white mb-2 text-balance">{heading}</h3>
      <p className="text-white/70 mb-7 max-w-md mx-auto leading-relaxed">{description}</p>
      <Link
        href={href}
        className="inline-flex items-center justify-center bg-[#047857] text-white font-semibold px-7 py-3.5 rounded-xl hover:bg-[#036546] hover:shadow-premium-lg transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0F2356]"
      >
        {label}
      </Link>
    </div>
  )
}
