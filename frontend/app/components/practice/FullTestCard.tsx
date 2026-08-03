import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { CompletedBadge } from '@/components/ui/CompletedBadge'

export function FullTestCard({
  title,
  meta,
  completed,
  onStart,
}: {
  title: string
  meta: string
  completed?: boolean
  onStart: () => void
}) {
  return (
    <Card className="relative p-6 flex flex-col gap-3 hover:shadow-md transition-all border-primary/20">
      {completed && <CompletedBadge />}
      <span className="px-3 py-1 rounded-full text-xs font-semibold w-fit bg-primary/10 text-primary">Full test</span>
      <h3 className="text-xl font-bold text-primary">{title}</h3>
      <p className="text-sm text-gray-500">{meta}</p>
      <Button onClick={onStart} className="w-full mt-auto">
        Start Full Test →
      </Button>
    </Card>
  )
}
