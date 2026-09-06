// Focused test for isModuleVisible() in AppShell.tsx (institution nav-visibility
// fix, Option 1: suppress the B2C free-trial bypass for institution members
// while keeping B2C-OR-institution access intact).
//
// No unit-test runner exists in this project (only Playwright e2e), and
// AppShell.tsx imports next/navigation, next/link, lucide-react, and several
// @/... app modules -- none resolvable by plain Node. Same approach as
// src/lib/api.upgrade.test.mjs: transpile the real AppShell.tsx source (via
// the `typescript` package already in devDependencies), run it in a small
// sandbox with those imports stubbed, then exercise the real, exported
// isModuleVisible() with Node's built-in test runner.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import vm from 'node:vm'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const appShellPath = path.join(import.meta.dirname, 'AppShell.tsx')
const source = fs.readFileSync(appShellPath, 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.React,
    esModuleInterop: true,
  },
})

const stubbedRequests = new Set([
  'react', 'next/link', 'next/navigation', '@/lib/supabase', 'lucide-react',
  '@/components/ui/SpeakOETLogo', '@/components/ErrorBoundary', '@/lib/api', '@/lib/consent',
])

const noop = () => {}
const IconStub = () => null

const mod = new Module(appShellPath)
mod.filename = appShellPath
mod.paths = Module._nodeModulePaths(path.dirname(appShellPath))
const originalResolve = Module._resolveFilename
Module._resolveFilename = function (request, ...rest) {
  if (stubbedRequests.has(request)) return request
  return originalResolve.call(this, request, ...rest)
}
mod.require = (request) => {
  switch (request) {
    case 'react':
      return { createContext: () => ({}), useContext: noop, useMemo: (fn) => fn(), useState: () => [undefined, noop], useEffect: noop, useRef: () => ({ current: null }) }
    case 'next/link':
      return { default: IconStub }
    case 'next/navigation':
      return { useRouter: () => ({}), usePathname: () => '' }
    case '@/lib/supabase':
      return { signOut: async () => {}, useSupabaseSession: () => ({ session: null, status: 'unauthenticated' }) }
    case 'lucide-react':
      return new Proxy({}, { get: () => IconStub })
    case '@/components/ui/SpeakOETLogo':
      return { default: IconStub }
    case '@/components/ErrorBoundary':
      return { ErrorBoundary: IconStub }
    case '@/lib/api':
      return { default: { get: async () => ({ data: {} }) } }
    case '@/lib/consent':
      return { openConsentPreferences: noop }
    default:
      return originalResolve ? require(request) : undefined
  }
}

vm.runInThisContext(Module.wrap(outputText))(
  mod.exports, mod.require, mod, mod.filename, path.dirname(appShellPath)
)
Module._resolveFilename = originalResolve

const { isModuleVisible, institutionNavGroup } = mod.exports

function usage(overrides) {
  return { sessions_used: 0, sessions_limit: 3, sessions_remaining: 3, plan: 'free', ...overrides }
}

// ── Normal B2C user: existing nav behavior is untouched ──────────────────

test('normal free B2C user (no institution membership): every module stays visible', () => {
  const u = usage({ plan: 'free' })
  for (const moduleKey of ['reading', 'listening', 'writing', 'mock_tests']) {
    assert.equal(isModuleVisible(moduleKey, u), true)
  }
})

test('items with no moduleKey (Dashboard, Speaking, Technique) are always visible', () => {
  assert.equal(isModuleVisible(undefined, usage({ plan: 'free' })), true)
  assert.equal(isModuleVisible(undefined, usage({ plan: 'free', is_institution_member: true, institution_modules: [] })), true)
})

test('no usage yet (still loading): nothing is hidden', () => {
  assert.equal(isModuleVisible('reading', null), true)
})

// ── Free-plan institution student: institution_modules controls visibility ──

test('free institution student, speaking-only institution: Reading/Listening/Writing/Mock hidden', () => {
  const u = usage({ plan: 'free', is_institution_member: true, institution_modules: ['speaking'] })
  for (const moduleKey of ['reading', 'listening', 'writing', 'mock_tests']) {
    assert.equal(isModuleVisible(moduleKey, u), false)
  }
})

test('free institution student: institution-enabled module is visible', () => {
  const u = usage({ plan: 'free', is_institution_member: true, institution_modules: ['speaking', 'reading'] })
  assert.equal(isModuleVisible('reading', u), true)
  assert.equal(isModuleVisible('listening', u), false)
})

// ── Paid B2C institution member: paid plan access is never erased ────────

test('pro + institution membership (speaking-only): Reading/Listening/Writing (Pro grants) stay visible, Mock (Elite-only) stays hidden', () => {
  const u = usage({ plan: 'pro', is_institution_member: true, institution_modules: ['speaking'] })
  assert.equal(isModuleVisible('reading', u), true)
  assert.equal(isModuleVisible('listening', u), true)
  assert.equal(isModuleVisible('writing', u), true)
  assert.equal(isModuleVisible('mock_tests', u), false) // matches existing non-institution Pro behavior
})

test('elite + institution membership: Mock Test stays visible (Elite grants it on its own)', () => {
  const u = usage({ plan: 'elite', is_institution_member: true, institution_modules: ['speaking'] })
  assert.equal(isModuleVisible('mock_tests', u), true)
})

// ── institutionNavGroup: Institution sidebar section role-gating ─────────

test('regular B2C user / no usage yet: no Institution nav section', () => {
  assert.equal(institutionNavGroup(null), null)
  assert.equal(institutionNavGroup(usage({ plan: 'free' })), null)
})

test('institution student (no admin role): no Institution nav section', () => {
  const u = usage({ plan: 'free', is_institution_member: true, institution_modules: ['speaking'] })
  assert.equal(institutionNavGroup(u), null)
})

test('teacher: Overview + Students, no Invitations', () => {
  const u = usage({ plan: 'free', institution_admin_role: 'teacher' })
  const group = institutionNavGroup(u)
  assert.equal(group.heading, 'Institution')
  assert.deepEqual(group.items.map((i) => i.label), ['Overview', 'Students'])
})

test('institution_admin: Overview + Students + Invitations', () => {
  const u = usage({ plan: 'free', institution_admin_role: 'institution_admin' })
  const group = institutionNavGroup(u)
  assert.deepEqual(group.items.map((i) => i.label), ['Overview', 'Students', 'Invitations'])
})
