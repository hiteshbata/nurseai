import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Privacy Policy - SpeakOET',
  description: 'How SpeakOET collects, uses, and protects your data.',
}

export default function PrivacyPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 py-20">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">
        Privacy Policy
      </h1>
      <p className="text-gray-500 text-center max-w-md">
        Our privacy policy is being updated.
        Contact support@speakoet.com for details.
      </p>
    </main>
  )
}
