// The Full Mock Test now lives at /practice/mock (alongside the sub-test players
// it chains). Keep this canonical URL working — redirect any old link there.
import { redirect } from 'next/navigation'

export default function MockTestRedirect() {
  redirect('/practice/mock')
}
