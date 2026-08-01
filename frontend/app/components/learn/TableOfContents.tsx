export function TableOfContents({ items }: { items: { id: string; label: string }[] }) {
  return (
    <nav className="mb-10 rounded-xl border border-gray-100 bg-[#F8FAFC] p-5" aria-label="Table of contents">
      <p className="text-sm font-semibold text-[#0F2356] mb-2">On this page</p>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className="text-sm text-gray-600 motion-safe:transition-colors motion-safe:duration-150 hover:text-[#0F2356] underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#047857] focus-visible:ring-offset-2"
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
