export default function Loading() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#F8FAFC]">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      <p className="mt-4 text-gray-500 text-sm">Loading writing practice...</p>
    </div>
  )
}
