import Image from 'next/image'
import type { PortableTextComponents } from '@portabletext/react'
import { urlForImage, type SanityImage } from '@/lib/sanity'
import { isSafeHref } from './link-safety'

// Sanity asset refs encode dimensions as "image-<id>-<width>x<height>-<format>",
// which avoids pulling in @sanity/asset-utils for one field.
function parseAssetDimensions(ref: string): { width: number; height: number } | null {
  const match = ref.match(/-(\d+)x(\d+)-/)
  if (!match) return null
  return { width: Number(match[1]), height: Number(match[2]) }
}

export const portableTextComponents: PortableTextComponents = {
  marks: {
    link: ({ children, value }) => {
      const href = typeof value?.href === 'string' ? value.href : undefined
      if (!href || !isSafeHref(href)) return <>{children}</>
      const isExternal = /^https?:/i.test(href.trim())
      return (
        <a
          href={href}
          className="text-[#047857] underline underline-offset-2 hover:text-[#0F2356]"
          {...(isExternal ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
        >
          {children}
        </a>
      )
    },
  },
  types: {
    image: ({ value }) => {
      const image = value as SanityImage | undefined
      const ref = image?.asset?._ref
      const dimensions = ref ? parseAssetDimensions(ref) : null
      if (!image || !ref || !dimensions) return null

      const width = 1600
      const height = Math.round((width * dimensions.height) / dimensions.width)
      const src = urlForImage(image).width(width).height(height).fit('max').auto('format').url()

      return (
        <span className="block my-8">
          <Image
            src={src}
            alt="Blog image"
            width={width}
            height={height}
            sizes="(min-width: 768px) 700px, 100vw"
            className="rounded-2xl w-full h-auto"
          />
        </span>
      )
    },
  },
}
