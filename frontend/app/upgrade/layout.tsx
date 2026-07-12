import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Upgrade Your Plan',
  description: 'Compare SpeakOET plans and pick the one that fits your OET Speaking prep.',
}

export default function UpgradeLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
