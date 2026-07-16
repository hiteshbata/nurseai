import './globals.css'
import { Navbar } from '@/components/Navbar'
import { Footer } from '@/components/Footer'
import Providers from './providers'
import type { Metadata } from 'next'
import ConditionalLayout from './conditional-layout'
import { SITE_URL, SITE_NAME, SITE_DESCRIPTION } from '@/lib/site'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} — OET Speaking Practice for Nurses`,
    template: `%s — ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  keywords: ['OET speaking', 'OET practice', 'OET for nurses', 'OET AI coach', 'OET band score'],
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    url: SITE_URL,
    siteName: SITE_NAME,
    title: `${SITE_NAME} — OET Speaking Practice for Nurses`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE_NAME} — OET Speaking Practice for Nurses`,
    description: SITE_DESCRIPTION,
  },
}

const organizationJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: SITE_NAME,
  url: SITE_URL,
  logo: `${SITE_URL}/logo-full.png`,
  description: SITE_DESCRIPTION,
  email: 'support@speakoet.com',
  sameAs: [
    'https://www.instagram.com/speakoet',
    'https://youtube.com/@speakoet',
    'https://www.linkedin.com/company/speak-oet/',
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd) }}
        />
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