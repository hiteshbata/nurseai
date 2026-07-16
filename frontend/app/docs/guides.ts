export interface DocsGuide {
  href: string
  title: string
  description: string
}

export const docsGuides: DocsGuide[] = [
  {
    href: '/docs/getting-started',
    title: 'Getting Started',
    description: 'Create your account, run your first AI patient roleplay, and understand your dashboard.',
  },
  {
    href: '/docs/practice-speaking',
    title: 'Practice Speaking',
    description: 'How the AI patient roleplay works, what the 9-criteria feedback means, and tips for getting the most out of a session.',
  },
  {
    href: '/docs/practice-writing',
    title: 'Practice Writing',
    description: 'How OET Writing practice works and which plans include it.',
  },
  {
    href: '/docs/account-and-billing',
    title: 'Account & Billing',
    description: 'Manage your plan, sessions, subscription, and account settings.',
  },
]
