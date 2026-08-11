import type { Metadata } from 'next'
import { Cookie } from 'lucide-react'
import { LegalLayout, type LegalSection } from '@/components/legal/LegalLayout'
import { ManageCookiePreferencesButton } from '@/components/consent/ManageCookiePreferencesButton'

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description: 'How SpeakOET uses cookies and similar technologies, and how to control them.',
  alternates: { canonical: '/cookies' },
}

const SECTIONS: LegalSection[] = [
  {
    heading: '1. What This Policy Covers',
    body: `This Cookie Policy explains how SpeakOET uses cookies and similar technologies -- such as browser local storage -- when you visit our web application. It should be read alongside our Privacy Policy, which explains more broadly how we handle your personal information.

This page describes our current practices. It is provided for transparency and does not constitute legal advice, and it does not itself guarantee compliance with every law in every jurisdiction our users access SpeakOET from.`,
  },
  {
    heading: '2. What Are Cookies and Similar Technologies',
    body: `Cookies are small text files a website can store on your device to remember information between visits, such as whether you're logged in. Similar technologies, like browser local storage, serve related purposes -- storing small pieces of data on your device that the application reads back later.

We use both. Where this policy says "cookies," it also covers the local storage we use for the same purpose.`,
  },
  {
    heading: '3. How We Categorize Cookies',
    body: `We group every cookie and similar technology SpeakOET uses into one of three categories: Necessary, Analytics, and Marketing. Necessary technologies always run. Analytics and Marketing only run once you give consent, and you can change that choice at any time.`,
    action: <ManageCookiePreferencesButton />,
  },
  {
    heading: '4. Necessary',
    body: `These keep SpeakOET secure and working, and cannot be switched off through our consent tool.

Authentication -- Supabase, our authentication provider, uses cookies and local storage to keep you signed in and to maintain your session securely across page loads.

Security -- Cloudflare Turnstile, our bot-protection service, uses cookies and similar technology to distinguish real visitors from automated abuse on sensitive actions like sign-up and study-plan generation.

Payments -- when you intentionally start a checkout, our payment provider (Razorpay) may set cookies needed to process that payment. These only load when you open the payment flow.`,
  },
  {
    heading: '5. Analytics',
    body: `Used only if you grant Analytics consent, to help us understand how SpeakOET is used so we can improve the product.

PostHog -- product analytics. Tracks how you navigate and use SpeakOET's features, and (when enabled) records sessions for product-improvement purposes. Delivered through our own proxy domain, data.speakoet.com.

Google Analytics -- aggregate traffic and usage measurement.

Neither loads, and neither sets any cookie or local storage entry, until you grant Analytics consent.`,
  },
  {
    heading: '6. Marketing',
    body: `Used only if you grant Marketing consent, to help us measure and improve how we reach prospective users.

Meta Pixel -- measures the effectiveness of our marketing on Meta platforms (Facebook/Instagram) and helps us understand which channels bring nurses to SpeakOET. This does not load, and does not set any cookie, until you grant Marketing consent.`,
  },
  {
    heading: '7. How Consent Works',
    body: `The first time you visit SpeakOET, you'll see a banner asking you to Accept all, Reject non-essential, or Manage preferences. Necessary technologies run either way, since the application can't function securely without them. Analytics and Marketing technologies stay off until you actively choose to enable them, either from the banner or from the preferences panel.

Your choice is remembered on this device (so you won't see the banner again on return visits) and is not shared with anyone beyond what's needed to run SpeakOET.`,
  },
  {
    heading: '8. Changing or Withdrawing Consent',
    body: `You can change your Analytics and Marketing preferences at any time -- there's no need to clear your browser data. Look for "Cookie Settings" in the site footer, or in the account menu if you're signed in, or use the button below.

When you disable a category you'd previously enabled, we stop that category's tracking going forward using each provider's supported controls.`,
    action: <ManageCookiePreferencesButton />,
  },
  {
    heading: '9. Browser Controls',
    body: `Most browsers also let you block or delete cookies directly in their settings, independent of the choice you make here. Blocking Necessary cookies through your browser may prevent you from signing in or using core SpeakOET features, since our consent tool cannot override a browser-level block.`,
  },
  {
    heading: '10. Changes to This Policy',
    body: `If the technologies we use, or the purposes we use them for, change materially, we'll update this page and may ask you to make a fresh consent choice. We encourage you to check back periodically.`,
  },
  {
    heading: '11. Contact Us',
    body: `Questions about this Cookie Policy can be sent to privacy@speakoet.com.`,
  },
]

export default function CookiesPage() {
  return (
    <LegalLayout
      icon={Cookie}
      title="Cookie Policy"
      effectiveDate="August 10, 2026"
      sections={SECTIONS}
    />
  )
}
