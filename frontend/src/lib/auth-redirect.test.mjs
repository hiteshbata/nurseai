// Unit tests for sanitizeNext() -- the server-side redirect-target validator
// used by app/auth/confirm/route.ts. No external imports in auth-redirect.ts,
// so (unlike api.upgrade.test.mjs) this just transpiles and runs it directly.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import vm from 'node:vm'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const srcPath = path.join(import.meta.dirname, 'auth-redirect.ts')
const source = fs.readFileSync(srcPath, 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  },
})

const mod = new Module(srcPath)
mod.filename = srcPath
mod.paths = Module._nodeModulePaths(path.dirname(srcPath))
mod._compile(outputText, srcPath)
const { sanitizeNext, resolveConfirmNext, maskEmail } = mod.exports

const ORIGIN = 'https://qa.speakoet.com'

test('relative path is passed through unchanged', () => {
  assert.equal(sanitizeNext('/auth/callback?returnTo=%2Fjoin%2Fabc123', ORIGIN), '/auth/callback?returnTo=%2Fjoin%2Fabc123')
})

test('protocol-relative //evil.example is rejected', () => {
  assert.equal(sanitizeNext('//evil.example', ORIGIN), null)
})

test('absolute external https://evil.example is rejected', () => {
  assert.equal(sanitizeNext('https://evil.example', ORIGIN), null)
})

test('absolute external with matching-looking path is still rejected', () => {
  assert.equal(sanitizeNext('https://evil.example/auth/callback', ORIGIN), null)
})

test('same-origin absolute URL is reduced to path+search', () => {
  assert.equal(sanitizeNext('https://qa.speakoet.com/auth/callback?returnTo=%2Fjoin%2Fabc123', ORIGIN), '/auth/callback?returnTo=%2Fjoin%2Fabc123')
})

test('null/empty next is rejected', () => {
  assert.equal(sanitizeNext(null, ORIGIN), null)
  assert.equal(sanitizeNext('', ORIGIN), null)
})

test('bare non-URL garbage is rejected', () => {
  assert.equal(sanitizeNext('not a url', ORIGIN), null)
})

// ── resolveConfirmNext: default redirect target for /auth/confirm ────────

test('type=invite with no explicit next defaults to reset-password?type=invite', () => {
  assert.equal(resolveConfirmNext('invite', null, ORIGIN), '/auth/reset-password?type=invite')
})

test('type=signup with no explicit next keeps the existing callback default', () => {
  assert.equal(resolveConfirmNext('signup', null, ORIGIN), '/auth/callback')
})

test('type=recovery with no explicit next keeps the existing callback default', () => {
  assert.equal(resolveConfirmNext('recovery', null, ORIGIN), '/auth/callback')
})

test('type=invite ignores an explicit same-origin next -- password setup is never skippable', () => {
  assert.equal(
    resolveConfirmNext('invite', '/auth/callback?returnTo=%2Fjoin%2Fabc123', ORIGIN),
    '/auth/reset-password?type=invite'
  )
})

test('type=invite with a malicious next still rejects it and falls back to the invite default', () => {
  assert.equal(resolveConfirmNext('invite', '//evil.example', ORIGIN), '/auth/reset-password?type=invite')
  assert.equal(resolveConfirmNext('invite', 'https://evil.example', ORIGIN), '/auth/reset-password?type=invite')
})

test('type=signup with a malicious next still rejects it and falls back to /auth/callback', () => {
  assert.equal(resolveConfirmNext('signup', '//evil.example', ORIGIN), '/auth/callback')
})

test('null type with no next falls back to /auth/callback (existing behavior)', () => {
  assert.equal(resolveConfirmNext(null, null, ORIGIN), '/auth/callback')
})

// ── maskEmail: safe display on /auth/verify ───────────────────────────────

test('maskEmail keeps first char and domain, stars the rest of the local part', () => {
  assert.equal(maskEmail('hitesh@gmail.com'), 'h*****@gmail.com')
})

test('maskEmail pads short local parts to at least 3 stars', () => {
  assert.equal(maskEmail('ab@gmail.com'), 'a***@gmail.com')
})

test('maskEmail returns the input unchanged if it has no @', () => {
  assert.equal(maskEmail('not-an-email'), 'not-an-email')
})
