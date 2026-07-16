import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-24 text-center">
      <p className="text-sm font-semibold text-accent">404</p>
      <h1 className="mt-2 text-3xl font-bold text-gray-900 sm:text-4xl">Page not found</h1>
      <p className="mt-4 max-w-md text-gray-600">
        The page you're looking for doesn't exist or may have moved. Let's get you back on track.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link href="/dashboard">
          <Button variant="default">Go to dashboard</Button>
        </Link>
        <Link href="/">
          <Button variant="outline">Back to home</Button>
        </Link>
      </div>
    </div>
  )
}
