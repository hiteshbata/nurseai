export interface OetCountryPage {
  slug: string
  label: string
  type: 'destination' | 'source'
}

export const OET_COUNTRY_PAGES: OetCountryPage[] = [
  { slug: 'uk', label: 'United Kingdom — NMC', type: 'destination' },
  { slug: 'australia', label: 'Australia — Ahpra/NMBA', type: 'destination' },
  { slug: 'ireland', label: 'Ireland — NMBI', type: 'destination' },
  { slug: 'new-zealand', label: 'New Zealand — Nursing Council', type: 'destination' },
  { slug: 'canada', label: 'Canada — provincial/territorial regulators', type: 'destination' },
  { slug: 'uae', label: 'UAE — DHA / DOH / MOHAP', type: 'destination' },
  { slug: 'india', label: 'India', type: 'source' },
  { slug: 'philippines', label: 'Philippines', type: 'source' },
]

export const OET_DESTINATION_PAGES = OET_COUNTRY_PAGES.filter((p) => p.type === 'destination')
