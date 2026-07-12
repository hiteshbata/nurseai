import { createClient } from '@sanity/client'
import imageUrlBuilder from '@sanity/image-url'

interface SanityImage {
  asset: { _ref: string; _type: 'reference' }
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
    `*[_type == "post"] | order(publishedAt desc) {
      _id, title, "slug": slug.current, excerpt, publishedAt, coverImage
    }`
  )
}

export async function getBlogPost(slug: string): Promise<BlogPost | null> {
  return sanityClient.fetch(
    `*[_type == "post" && slug.current == $slug][0] {
      _id, title, "slug": slug.current, excerpt, body, publishedAt, coverImage
    }`,
    { slug }
  )
}
