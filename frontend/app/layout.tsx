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
  verification: {
    google: process.env.GOOGLE_SITE_VERIFICATION || undefined,
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-md focus:bg-emerald-700 focus:px-4 focus:py-2 focus:text-white focus:outline-none focus:ring-2 focus:ring-white"
        >
          Skip to content
        </a>
        <Providers>
          <ConditionalLayout>{children}</ConditionalLayout>
        </Providers>
      </body>
    </html>
  )
}