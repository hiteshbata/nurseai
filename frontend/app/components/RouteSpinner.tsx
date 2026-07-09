export function RouteSpinner({
  message,
  bg = "bg-[#F8FAFC]",
  border = "border-blue-500",
}: {
  message?: string
  bg?: string
  border?: string
}) {
  return (
    <div className={`min-h-screen flex flex-col items-center justify-center ${bg}`}>
      <div className={`animate-spin rounded-full h-12 w-12 border-b-2 ${border}`} />
      {message && <p className="mt-4 text-gray-500 text-sm">{message}</p>}
    </div>
  )
}
