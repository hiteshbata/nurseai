import './globals.css'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'
import Providers from './providers'
import type { Metadata } from 'next'
import ConditionalLayout from './conditional-layout'

export const metadata: Metadata = {
  title: 'SpeakOET — OET Speaking Practice for Nurses',
  description: 'AI-powered OET speaking preparation for nurses. Practice roleplays, get real-time AI feedback, and track your band score progress.',
  icons: {
    icon: '/favicon.svg',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <Providers>
          <ConditionalLayout>{children}</ConditionalLayout>
        </Providers>
      </body>
    </html>
  )
}