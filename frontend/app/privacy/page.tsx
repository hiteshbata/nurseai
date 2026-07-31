import type { Metadata } from 'next'
import { ShieldCheck } from 'lucide-react'
import { LegalLayout } from '@/components/legal/LegalLayout'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How SpeakOET collects, uses, and protects your data.',
  alternates: { canonical: '/privacy' },
}

const SECTIONS: { heading: string; body: string }[] = [
  {
    heading: '1. Introduction',
    body: `Welcome to SpeakOET. At SpeakOET, we believe that preparing for the Occupational English Test (OET) should be a seamless, focused, and secure experience. We are strongly committed to protecting your personal information and your right to privacy.

This Privacy Policy explains in simple terms how we collect, use, and protect your information when you use the SpeakOET web application and related services. Our primary goal is to be completely transparent about our data practices so that you can feel confident and secure while using our platform. We designed this policy to be straightforward, avoiding complicated legal jargon wherever possible.

By accessing, creating an account, or otherwise using SpeakOET, you acknowledge that you have read and understood this Privacy Policy and agree to the practices described herein. If you have any questions or concerns about this policy, please reach out to us.`,
  },
  {
    heading: '2. Information We Collect',
    body: `We believe in data minimization, meaning we collect only the information that is absolutely necessary to provide you with a high-quality service. The information we gather falls into a few distinct categories based on how you interact with our platform.

Information You Provide to Us Directly:

Account Information: When you register for a SpeakOET account, we collect your name and email address. If you choose the convenience of signing in via a third-party authentication service like Google, we receive basic profile information, such as your name and email address, directly from that provider to establish your account.

Profile Data: We collect any additional information you choose to add to your user profile to personalize your learning experience.

Practice and Assessment Data: Because SpeakOET is specifically designed to help healthcare professionals practice OET speaking, we collect and process the audio recordings of your speaking practice sessions. For live voice roleplay sessions, we also generate and store a text transcript of the conversation, which we retain for up to 90 days for quality assurance and account safety review before it is automatically deleted. Furthermore, we store the AI-generated feedback, your performance scores, and your historical progress metrics. This allows you to effectively track your improvement over time.

Support Communications: If you contact us for customer support, technical assistance, or general inquiries, we collect your contact details and the contents of your messages to assist you effectively.

Information We Collect Automatically:

Usage Information: When you access our application, we automatically log standard information about how you interact with our platform. This includes basic connection data, session durations, and the specific features you utilize. We collect this solely to ensure our application functions correctly and to identify areas where we can improve the user experience.`,
  },
  {
    heading: '3. How We Use Your Information',
    body: `We use the information we collect strictly to operate, maintain, and improve the SpeakOET platform. Specifically, we use your data to:

Provide the Core Service: We process your practice audio to generate personalized AI feedback, calculate your speaking scores, and display your progress tracking dashboard. This is the fundamental purpose of our application.

Manage Your Account: We use your information to create your account, manage your subscription status, authenticate your logins, and secure your profile.

Communicate With You: We use your email address to send you essential service updates, security alerts, and administrative messages. If you opt in, we may also send you tips for OET preparation and platform updates.

Provide Customer Support: We use your information to resolve technical issues, respond to your inquiries, and provide personalized assistance when you reach out to our support team.

Improve Our Platform: We analyze aggregated usage data to understand how users navigate our application, allowing us to fix bugs, optimize performance, and develop new features that better serve healthcare professionals preparing for the OET.`,
  },
  {
    heading: '4. How We Share Information',
    body: `We value your privacy and do not sell your personal information to third parties. We only share your information under the following specific circumstances:

Trusted Third-Party Service Providers: We may share your information with carefully selected third-party service providers who assist us in operating our application. These trusted partners include hosting providers, AI processing services, email communication platforms, and secure analytics tools. These providers are strictly authorized to use your information only as necessary to provide these essential services to us.

Business Transfers: In the event that SpeakOET is involved in a merger, acquisition, reorganization, or sale of assets, your personal information may be transferred as part of that transaction. We will ensure that the receiving party agrees to respect your privacy in a manner consistent with this Privacy Policy.

Legal Obligations: We may disclose your information if we are required to do so by law, regulation, or a valid legal request from a government or law enforcement agency. We will only disclose information to the extent strictly necessary to comply with our legal obligations or to protect the rights, safety, and property of SpeakOET, our users, or the public.`,
  },
  {
    heading: '5. Payments',
    body: `SpeakOET offers paid subscription plans to access advanced features. We process all payments securely through an established, industry-leading third-party payment provider.

When you purchase a subscription, you provide your payment information directly to this secure payment processor. SpeakOET does not process, capture, or store your full credit card details or bank account numbers on our servers. We only receive limited transaction data, such as a billing token, confirmation of payment success, and the last four digits of your card, which we use to manage your subscription status and prevent fraud.`,
  },
  {
    heading: '6. Cookies',
    body: `Like most modern web applications, SpeakOET uses cookies and similar simple technologies to ensure our platform functions correctly. Cookies are small text files stored on your device that help us recognize you when you return.

We primarily use essential cookies, which are strictly necessary to keep you logged in, maintain your session securely, and remember your basic preferences. We may also use basic performance cookies to understand how users interact with our application so we can make improvements. You can choose to disable non-essential cookies through your web browser settings, though doing so may limit your ability to use certain features of SpeakOET smoothly.`,
  },
  {
    heading: '7. Data Security',
    body: `We take the security of your personal and practice data seriously. SpeakOET employs reasonable, industry-standard administrative, technical, and physical security measures to protect your information against unauthorized access, loss, destruction, or alteration.

While we strive to use commercially acceptable means to protect your personal data, it is important to remember that no method of transmission over the Internet, and no method of electronic storage, is entirely foolproof. Therefore, while we are committed to safeguarding your information, we cannot guarantee its absolute security. We encourage you to protect your account by choosing a strong password and keeping your login credentials confidential.`,
  },
  {
    heading: '8. Your Rights',
    body: `Depending on your location, you may have specific rights regarding your personal information. Regardless of your legal jurisdiction, SpeakOET is committed to providing all our users with fundamental control over their data. Your rights include:

Right to Access: You have the right to request a copy of the personal information we currently hold about you.

Right to Update and Correct: You have the right to request that we correct any inaccurate or incomplete information associated with your account. You can also update most of your profile details directly within the application.

Right to Delete: You have the right to request that we permanently delete your personal information and close your account. When you request deletion, we will remove your personal data from our active systems, except where we are legally required to retain certain records (such as transaction history for tax purposes).

Right to Withdraw Consent: Where we rely on your consent to process your information, you have the right to withdraw that consent at any time.

To exercise any of these rights, please contact us using the information provided at the bottom of this Privacy Policy. We will respond to your request promptly and in accordance with applicable laws.`,
  },
  {
    heading: "9. Children's Privacy",
    body: `SpeakOET is designed and intended exclusively for adult healthcare professionals preparing for professional certification. Our service is not directed at, nor do we knowingly collect personal information from, children under the age of 18.

If we become aware that we have inadvertently collected personal information from a child under 18 without appropriate parental consent, we will take immediate steps to securely delete that information from our servers. If you believe we might have any information from or about a child under 18, please contact us immediately.`,
  },
  {
    heading: '10. Changes to This Privacy Policy',
    body: `We may update this Privacy Policy from time to time to reflect changes in our practices, new features, or updates to applicable legal requirements.

When we make significant changes, we will notify you by sending an email to the address associated with your account or by displaying a prominent notice within the SpeakOET application before the changes become effective. We encourage you to review this page periodically to stay informed about how we are protecting your privacy. Your continued use of the service after any changes to this Privacy Policy constitutes your acceptance of the revised terms.`,
  },
  {
    heading: '11. Contact Us',
    body: `If you have any questions, concerns, or feedback regarding this Privacy Policy, or if you would like to exercise any of your data rights, please do not hesitate to reach out to us. We are here to help.

You can contact our privacy team at:

Email: privacy@speakoet.com

We aim to review and respond to all inquiries as quickly as possible.`,
  },
]

export default function PrivacyPage() {
  return (
    <LegalLayout
      icon={ShieldCheck}
      title="Privacy Policy"
      effectiveDate="July 21, 2026"
      sections={SECTIONS}
    />
  )
}
