import Link from 'next/link'
import Image from 'next/image'
import type { Metadata } from 'next'
import { learnArticles } from '../../learn/articles'
import { getBlogPosts, urlForImage, type BlogPost } from '@/lib/sanity'
import { RevealOnScroll } from '@/components/RevealOnScroll'

const cardClass =
  'block rounded-2xl border border-gray-100 bg-white shadow-premium overflow-hidden motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2'

export const revalidate = 60

export const metadata: Metadata = {
  title: 'Blog',
  description:
    'Guides on OET Speaking: exam format, band scores, OET vs IELTS, speaking tips, and advice for Indian nurses.',
  alternates: { canonical: '/blog' },
  openGraph: {
    type: 'website',
    url: '/blog',
    siteName: 'SpeakOET',
    title: 'Blog — SpeakOET',
    description:
      'Guides on OET Speaking: exam format, band scores, OET vs IELTS, speaking tips, and advice for Indian nurses.',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Blog — SpeakOET',
    description:
      'Guides on OET Speaking: exam format, band scores, OET vs IELTS, speaking tips, and advice for Indian nurses.',
  },
}

function formatDate(date: string) {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function BlogCard({ post }: { post: BlogPost }) {
  return (
    <Link href={`/blog/${post.slug}`} className={cardClass}>
      <div className="relative aspect-[1200/630] w-full bg-gray-100">
        {post.coverImage ? (
          <Image
            src={urlForImage(post.coverImage).width(1200).height(630).url()}
            alt={post.title}
            fill
            sizes="(min-width: 640px) 50vw, 100vw"
            className="object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[#0F2356]/20 font-display text-4xl font-semibold">
            OET
          </div>
        )}
      </div>
      <div className="p-6">
        <h2 className="font-display text-lg font-semibold text-[#0F2356] mb-1">{post.title}</h2>
        {post.excerpt && <p className="text-gray-500 text-sm mb-3">{post.excerpt}</p>}
        <p className="text-gray-400 text-xs">{formatDate(post.publishedAt)}</p>
      </div>
    </Link>
  )
}

export default async function BlogPage() {
  let posts: BlogPost[] = []
  try {
    posts = await getBlogPosts()
  } catch (err) {
    console.error('Failed to load blog posts', err)
  }

  return (
    <main className="min-h-screen px-4 py-20 max-w-4xl mx-auto">
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mb-4">Blog</h1>
        <p className="text-gray-500 text-lg mb-10">
          Guides on OET Speaking — format, scoring, and how to actually prepare.
        </p>
      </div>

      {posts.length > 0 ? (
        <div className="grid sm:grid-cols-2 gap-6 mb-16">
          {posts.map((post, i) => (
            <RevealOnScroll key={post._id} delayMs={Math.min(i, 4) * 40}>
              <BlogCard post={post} />
            </RevealOnScroll>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-gray-100 bg-white shadow-premium p-10 text-center mb-16">
          <p className="font-display text-lg font-semibold text-[#0F2356] mb-1">No articles yet</p>
          <p className="text-gray-500 text-sm">New OET resources are coming soon.</p>
        </div>
      )}

      <h2 className="font-display text-xl font-semibold text-[#0F2356] mb-4">More guides</h2>
      <div className="space-y-4">
        {learnArticles.map((article, i) => (
          <RevealOnScroll key={article.href} delayMs={Math.min(i, 4) * 40}>
            <Link
              href={article.href}
              className="block rounded-2xl border border-gray-100 bg-white shadow-premium p-6 motion-safe:transition-shadow motion-safe:duration-200 hover:shadow-premium-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
            >
              <h3 className="font-display text-lg font-semibold text-[#0F2356] mb-1">{article.title}</h3>
              <p className="text-gray-500 text-sm">{article.description}</p>
            </Link>
          </RevealOnScroll>
        ))}
      </div>
    </main>
  )
}
