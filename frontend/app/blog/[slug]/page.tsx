import Link from 'next/link'
import Image from 'next/image'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { PortableText } from '@portabletext/react'
import { getBlogPost, urlForImage } from '@/lib/sanity'
import { ArticleMeta } from '@/components/learn/ArticleMeta'
import { portableTextComponents } from './portable-text-components'
import { SITE_URL } from '@/lib/site'

export const revalidate = 60

// Escapes `<` so a title/excerpt containing "</script>" can't terminate the
// JSON-LD script element early -- < is a valid JSON string escape.
function jsonLdScript(data: unknown) {
  return JSON.stringify(data).replace(/</g, '\\u003c')
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string }
}): Promise<Metadata> {
  const post = await getBlogPost(params.slug)
  if (!post) return {}

  const canonicalPath = `/blog/${post.slug}`
  const ogImage = post.coverImage
    ? [{ url: urlForImage(post.coverImage).width(1200).height(630).fit('crop').url() }]
    : undefined

  return {
    title: post.title,
    description: post.excerpt,
    alternates: { canonical: canonicalPath },
    openGraph: {
      type: 'article',
      title: post.title,
      description: post.excerpt,
      url: canonicalPath,
      publishedTime: post.publishedAt,
      images: ogImage,
    },
    twitter: {
      card: 'summary_large_image',
      title: post.title,
      description: post.excerpt,
      images: ogImage?.map((image) => image.url),
    },
  }
}

export default async function BlogPostPage({ params }: { params: { slug: string } }) {
  const post = await getBlogPost(params.slug)
  if (!post) notFound()

  const blogPostingJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    headline: post.title,
    description: post.excerpt,
    datePublished: post.publishedAt,
    mainEntityOfPage: `${SITE_URL}/blog/${post.slug}`,
    ...(post.coverImage
      ? { image: urlForImage(post.coverImage).width(1200).height(630).fit('crop').url() }
      : {}),
  }

  return (
    <main className="min-h-screen px-4 py-20 max-w-3xl mx-auto">
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: jsonLdScript(blogPostingJsonLd) }}
      />
      <Link
        href="/blog"
        className="text-sm text-gray-500 motion-safe:transition-colors motion-safe:duration-150 hover:text-[#0F2356] rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
      >
        ← All articles
      </Link>
      <div className="motion-safe:animate-[fade-up-in_0.5s_ease-out_both]">
        <h1 className="font-display text-3xl font-semibold text-[#0F2356] mt-4 mb-4">{post.title}</h1>
        <ArticleMeta date={post.publishedAt} />
      </div>

      {post.coverImage && (
        <Image
          src={urlForImage(post.coverImage).width(1200).height(630).url()}
          alt={post.title}
          width={1200}
          height={630}
          className="rounded-2xl mb-8 w-full h-auto"
        />
      )}

      <div className="prose prose-gray max-w-none text-gray-600 leading-relaxed">
        <PortableText value={post.body} components={portableTextComponents} />
      </div>
    </main>
  )
}
