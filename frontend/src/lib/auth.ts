import { getServerSession } from 'next-auth'

export async function getCurrentUser() {
  const session = await getServerSession()
  return session?.user
}

export async function isAuthenticated() {
  const session = await getServerSession()
  return !!session
}
