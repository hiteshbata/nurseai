export function ArticleMeta({ date }: { date: string }) {
  const formatted = new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  return <p className="text-sm text-muted-foreground mb-8">By SpeakOET Team · {formatted}</p>
}
