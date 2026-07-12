import Link from 'next/link'
import type { Metadata } from 'next'
import { learnArticles } from '../learn/articles'
import { getBlogPosts } from '@/lib/sanity'

export const revalidate = 60

export const metadata: Metadata = {
  title: 'Blog',
  description:
    'Guides on OET Speaking: exam format, band scores, OET vs IELTS, speaking tips, and advice for Indian nurses.',
}

export default async function BlogPage() {
  const posts = await getBlogPosts()

  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-[#0F2356] mb-4">Blog</h1>
      <p className="text-gray-500 text-lg mb-10">
        Guides on OET Speaking — format, scoring, and how to actually prepare.
      </p>

      <div className="space-y-4 mb-10">
        {posts.map((post) => (
          <Link
            key={post._id}
            href={`/blog/${post.slug}`}
            className="block rounded-2xl border border-gray-100 bg-white shadow-sm p-6 hover:shadow-md transition"
          >
            <h2 className="text-lg font-bold text-[#0F2356] mb-1">{post.title}</h2>
            <p className="text-gray-500 text-sm">{post.excerpt}</p>
          </Link>
        ))}
      </div>

      <div className="space-y-4">
        {learnArticles.map((article) => (
          <Link
            key={article.href}
            href={article.href}
            className="block rounded-2xl border border-gray-100 bg-white shadow-sm p-6 hover:shadow-md transition"
          >
            <h2 className="text-lg font-bold text-[#0F2356] mb-1">{article.title}</h2>
            <p className="text-gray-500 text-sm">{article.description}</p>
          </Link>
        ))}
      </div>
    </main>
  )
}
