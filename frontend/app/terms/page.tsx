import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Terms & Conditions',
  description: 'The terms governing your use of SpeakOET.',
}

const SECTIONS: { heading: string; body: string }[] = [
  {
    heading: '1. Acceptance of Terms',
    body: `Welcome to SpeakOET. These Terms & Conditions ("Terms") form a legally binding agreement between you and SpeakOET ("we," "us," or "our") governing your access to and use of the SpeakOET web application and all associated services (collectively, the "Service").

By creating an account, accessing, or otherwise using the Service, you confirm that you have read, understood, and unconditionally agree to be bound by these Terms. If you do not agree to these Terms, you must not access or use SpeakOET. We reserve the right to restrict or terminate your access to the Service if you violate any of the provisions outlined in this agreement.`,
  },
  {
    heading: '2. Eligibility',
    body: `SpeakOET is intended for use by adult healthcare professionals preparing for the Occupational English Test (OET). By using our Service, you represent and warrant that you are at least 18 years of age and possess the legal capacity to enter into a binding contract. If you are using the Service on behalf of an organization, you represent that you have the authority to bind that organization to these Terms. Our Service is not directed at children, and we do not knowingly permit individuals under the age of 18 to create accounts.`,
  },
  {
    heading: '3. User Accounts',
    body: `To access the core features of SpeakOET, including OET speaking practice and AI-generated feedback, you must register for a user account.

You may create an account using your email address or through a supported third-party authentication service, such as Google.

You are entirely responsible for maintaining the confidentiality and security of your account credentials. You agree not to share your login details with any third party. You are responsible for all activities that occur under your account, whether or not you have authorized such activities. If you suspect any unauthorized access or a security breach related to your account, you must notify us immediately. SpeakOET cannot and will not be liable for any loss or damage arising from your failure to protect your account credentials.`,
  },
  {
    heading: '4. Acceptable Use',
    body: `We strive to maintain a safe, respectful, and effective educational environment. When using SpeakOET, you agree to use the Service only for its intended purpose and in compliance with all applicable laws.

You explicitly agree that you will not:

Misuse the platform or use it for any illegal or unauthorized purpose.

Attempt to gain unauthorized access to our systems, networks, or other users' accounts.

Upload, transmit, or share any audio, text, or other content that is harmful, offensive, discriminatory, defamatory, or otherwise objectionable.

Interfere with, disrupt, or compromise the integrity and performance of the Service.

Reverse engineer, decompile, disassemble, or attempt to discover the source code or underlying algorithms of SpeakOET.

Use automated scripts, bots, or scrapers to extract data from the Service.

Resell, sublicense, or commercially exploit any part of the Service without our express written permission.

We reserve the right to investigate and take appropriate action, including account suspension or termination, against anyone who violates these acceptable use standards.`,
  },
  {
    heading: '5. Subscription Plans and Payments',
    body: `SpeakOET offers paid subscription plans that grant access to advanced practice features, detailed AI feedback, and progress tracking.

When you select a subscription plan, you agree to pay all applicable fees associated with that plan. Subscription fees are charged according to the selected billing cycle and are billed in advance. All payments are processed securely by our authorized third-party payment provider. SpeakOET does not directly process or store your full credit card details.

By providing your payment information, you authorize us and our payment processor to charge the applicable fees to your designated payment method. If your payment method fails or is declined, we may suspend your access to the paid features of the Service until the outstanding balance is resolved.`,
  },
  {
    heading: '6. Refunds and Cancellation',
    body: `You may cancel your SpeakOET subscription at any time through your account settings. When you cancel, your cancellation will take effect at the end of your current paid billing cycle. You will retain access to your paid features until that cycle concludes.

Refunds for subscription fees are governed exclusively by our published refund policy, if applicable. Unless otherwise stated in the refund policy or required by law, all subscription fees are non-refundable, and we do not provide prorated refunds for partial months or unused time.`,
  },
  {
    heading: '7. AI-Generated Feedback Disclaimer',
    body: `SpeakOET utilizes artificial intelligence to provide feedback, scoring estimates, and insights on your OET speaking practice. It is critical to understand the limitations of this technology.

Educational Purposes Only: SpeakOET is an educational practice platform designed to supplement your study efforts. The AI-generated feedback is provided for learning purposes only. While we strive to make our AI evaluations helpful, they may not always be completely accurate, perfectly aligned with official OET grading rubrics, or free from error.

No Guarantees: SpeakOET does not guarantee any specific OET exam score, a passing result, or any subsequent outcomes dependent on the OET. Furthermore, SpeakOET makes no guarantees regarding visa approvals, employment opportunities, professional registration, or medical licensure. Your actual performance on the official OET exam will depend on numerous factors outside of our control. You should not rely solely on SpeakOET's AI feedback for official exam readiness.`,
  },
  {
    heading: '8. Intellectual Property',
    body: `Trademark Disclaimer: SpeakOET is an independent educational platform. The Occupational English Test (OET) is a registered trademark of Cambridge Boxhill Language Assessment Pty Ltd (CBLA). SpeakOET is not affiliated with, endorsed by, sponsored by, or associated with CBLA or the official Occupational English Test in any way.

The SpeakOET application, including its design, text, graphics, logos, user interfaces, software code, and overall "look and feel," is the exclusive property of SpeakOET and is protected by copyright, trademark, and other intellectual property laws.

These Terms do not grant you any ownership rights or licenses to our intellectual property, except for the limited, non-exclusive, non-transferable, and revocable right to access and use the Service for your personal, non-commercial educational purposes in accordance with these Terms.`,
  },
  {
    heading: '9. User Content',
    body: `As part of the Service, you will submit audio recordings of your speaking practice, text inputs, and other profile information ("User Content").

You retain full ownership of all intellectual property rights in the User Content you submit to SpeakOET. However, to provide the Service to you, we require certain permissions. By submitting User Content, you grant SpeakOET a worldwide, royalty-free, non-exclusive license to use, store, process, reproduce, and analyze your content solely for the purpose of operating the Service, providing you with AI-generated feedback and scores, and maintaining your practice history.

You represent and warrant that you have all necessary rights to submit your User Content and that your content does not violate the rights of any third party or any applicable laws.`,
  },
  {
    heading: '10. Service Availability',
    body: `We work diligently to ensure SpeakOET is available and functioning properly. However, we cannot guarantee uninterrupted access to the Service. The Service may be temporarily unavailable due to scheduled maintenance, software updates, unexpected technical issues, server outages, or factors beyond our reasonable control.

We will make reasonable efforts to minimize downtime and notify you in advance of scheduled maintenance when possible. SpeakOET shall not be held liable for any inconvenience, loss, or damage resulting from the temporary unavailability of the Service.`,
  },
  {
    heading: '11. Account Suspension or Termination',
    body: `We reserve the right to suspend or terminate your account and your access to the Service at our sole discretion, without prior notice or liability, for any reason, including but not limited to a breach of these Terms.

If we terminate your account due to a violation of our Acceptable Use policy, you will not be entitled to any refund for unused subscription time. Upon termination, your right to use the Service will immediately cease. Sections of these Terms that by their nature should survive termination (such as Intellectual Property, Disclaimer, Limitation of Liability, and Governing Law) shall remain in effect.`,
  },
  {
    heading: '12. Limitation of Liability',
    body: `To the maximum extent permitted by applicable law, SpeakOET, its founders, employees, partners, and service providers shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including but not limited to loss of profits, data, goodwill, or other intangible losses, resulting from:

Your access to, use of, or inability to access or use the Service;

Any reliance placed by you on the completeness, accuracy, or existence of any AI-generated feedback or scores;

Any unauthorized access to or alteration of your transmissions or data;

Any conduct or content of any third party on the Service.

In no event shall our aggregate liability for all claims related to the Service exceed the total amount paid by you to SpeakOET for the Service during the twelve (12) months immediately preceding the date the claim arose.`,
  },
  {
    heading: '13. Indemnification',
    body: `You agree to defend, indemnify, and hold harmless SpeakOET and its officers, directors, employees, and agents from and against any and all claims, damages, obligations, losses, liabilities, costs, or debt, and expenses (including attorney's fees) arising from your use of and access to the Service, your violation of these Terms, your violation of any third-party right, or your User Content causing damage to a third party.`,
  },
  {
    heading: '14. Third-Party Services',
    body: `SpeakOET integrates with various third-party services and links to external websites to enhance your experience, such as Google for authentication and third-party gateways for payment processing.

These third-party services operate independently of SpeakOET and are governed by their own terms of service and privacy policies. We do not control, endorse, or assume responsibility for the content or practices of any third-party websites or services. You acknowledge and agree that SpeakOET shall not be responsible or liable, directly or indirectly, for any damage or loss caused by your use of any such third-party services.`,
  },
  {
    heading: '15. Changes to the Terms',
    body: `We may update or modify these Terms & Conditions from time to time to reflect changes in our business, the Service, or legal requirements.

If we make material changes to these Terms, we will notify you by sending an email to the address associated with your account or by posting a prominent notice within the SpeakOET application prior to the changes taking effect. The "Effective Date" at the top of this document indicates when the latest modifications were made. Your continued use of the Service after the revised Terms become effective constitutes your acceptance of the updated Terms. If you do not agree to the new Terms, you must stop using the Service.`,
  },
  {
    heading: '16. Governing Law and Jurisdiction',
    body: `These Terms & Conditions shall be governed by and construed in accordance with the laws of India, without regard to its conflict of law provisions. Any legal action or proceeding arising under or related to these Terms or your use of the Service shall be brought exclusively in the courts of competent jurisdiction in India, and you hereby consent to the personal jurisdiction and venue therein.`,
  },
  {
    heading: '17. Contact Information',
    body: `We welcome your questions and feedback regarding these Terms & Conditions. If you have any inquiries or wish to report a violation of these Terms, please contact us.

Email: support@speakoet.com

We will do our best to address your concerns promptly and professionally.`,
  },
]

export default function TermsPage() {
  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-2">Terms &amp; Conditions</h1>
      <p className="text-gray-500 text-sm mb-10">Effective Date: July 12, 2026</p>

      <div className="space-y-10">
        {SECTIONS.map(({ heading, body }) => (
          <section key={heading}>
            <h2 className="text-xl font-bold text-[#0F2356] mb-3">{heading}</h2>
            {body.split('\n\n').map((paragraph, i) => (
              <p key={i} className="text-gray-600 leading-relaxed mb-3 last:mb-0 whitespace-pre-line">
                {paragraph}
              </p>
            ))}
          </section>
        ))}
      </div>
    </main>
  )
}
