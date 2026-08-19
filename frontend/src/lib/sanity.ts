import { cache } from 'react'
import { createClient } from '@sanity/client'
import imageUrlBuilder from '@sanity/image-url'

export interface SanityImage {
  asset: { _ref: string; _type: 'reference' }
  hotspot?: { x: number; y: number; height: number; width: number }
  crop?: { top: number; bottom: number; left: number; right: number }
}

export const sanityClient = createClient({
  projectId: process.env.NEXT_PUBLIC_SANITY_PROJECT_ID,
  dataset: process.env.NEXT_PUBLIC_SANITY_DATASET || 'production',
  apiVersion: '2026-07-01',
  useCdn: true,
})

const builder = imageUrlBuilder(sanityClient)
export function urlForImage(source: SanityImage) {
  return builder.image(source)
}

export interface BlogPost {
  _id: string
  title: string
  slug: string
  excerpt: string
  body: { _type: string; [key: string]: unknown }[]
  publishedAt: string
  coverImage?: SanityImage
}

export async function getBlogPosts(): Promise<BlogPost[]> {
  return sanityClient.fetch(
    `*[_type == "post" && defined(slug.current) && defined(publishedAt)] | order(publishedAt desc) {
      _id, title, "slug": slug.current, excerpt, publishedAt, coverImage
    }`
  )
}

// cache() dedupes this within a single render pass -- generateMetadata() and
// the page component both call getBlogPost() for the same slug.
export const getBlogPost = cache(async (slug: string): Promise<BlogPost | null> => {
  return sanityClient.fetch(
    `*[_type == "post" && slug.current == $slug && defined(publishedAt)][0] {
      _id, title, "slug": slug.current, excerpt, body, publishedAt, coverImage
    }`,
    { slug }
  )
})
