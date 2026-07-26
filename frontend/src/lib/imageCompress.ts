// Downscale + JPEG-compress a photo client-side before upload. A full-resolution
// phone camera photo is commonly 3-8MB; on a slow mobile hotspot that alone can
// blow past any reasonable timeout. OCR doesn't need full resolution, so shrink
// to a max dimension and re-encode -- typically a 10-20x size cut with no
// visible quality loss for reading handwriting.
const MAX_DIMENSION = 1600
const JPEG_QUALITY = 0.8

export async function compressImageToBase64(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height))
  const width = Math.round(bitmap.width * scale)
  const height = Math.round(bitmap.height * scale)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas not supported')
  ctx.drawImage(bitmap, 0, 0, width, height)
  bitmap.close()

  const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY)
  return dataUrl.split(',')[1] || ''
}
