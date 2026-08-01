import Link from 'next/link'
import type { Metadata } from 'next'
import { learnArticles } from '../learn/articles'
import { getBlogPosts } from '@/lib/sanity'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const cardClass =
  'block rounded-2xl border border-gray-100 bg-white shadow-premium p-6 motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2'

export const revalidate = 60

export const metadata: Metadata = {
  title: 'Blog',
  description:
    'Guides on OET Speaking: exam format, band scores, OET vs IELTS, speaking tips, and advice for Indian nurses.',
  alternates: { canonical: '/blog' },
}

export default async function BlogPage() {
  const posts = await getBlogPosts()

  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mb-4">Blog</h1>
        <p className="text-gray-500 text-lg mb-10">
          Guides on OET Speaking — format, scoring, and how to actually prepare.
        </p>
      </div>

      <div className="space-y-4 mb-10">
        {posts.map((post, i) => (
          <RevealOnScroll key={post._id} delayMs={Math.min(i, 4) * 40}>
            <Link href={`/blog/${post.slug}`} className={cardClass}>
              <h2 className="font-display text-lg font-semibold text-[#0F2356] mb-1">{post.title}</h2>
              <p className="text-gray-500 text-sm">{post.excerpt}</p>
            </Link>
          </RevealOnScroll>
        ))}
      </div>

      <div className="space-y-4">
        {learnArticles.map((article, i) => (
          <RevealOnScroll key={article.href} delayMs={Math.min(i, 4) * 40}>
            <Link href={article.href} className={cardClass}>
              <h2 className="font-display text-lg font-semibold text-[#0F2356] mb-1">{article.title}</h2>
              <p className="text-gray-500 text-sm">{article.description}</p>
            </Link>
          </RevealOnScroll>
        ))}
      </div>
    </main>
  )
}
