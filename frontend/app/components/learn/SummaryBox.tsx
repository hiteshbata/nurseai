export function SummaryBox({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div className="mb-8 rounded-2xl border border-gray-100 bg-[#F8FAFC] p-6">
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
        {rows.map((row) => (
          <div key={row.label} className="flex justify-between sm:justify-start gap-3 text-sm">
            <dt className="text-gray-500 font-medium">{row.label}</dt>
            <dd className="text-[#0F2356] font-semibold text-right sm:text-left">{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
