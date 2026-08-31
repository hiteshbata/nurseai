// Unit tests for the pure param-checks in reset-password/page.tsx
// (see helpers.ts). No external imports, so this just transpiles and runs
// it directly, same pattern as auth-redirect.test.mjs.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const srcPath = path.join(import.meta.dirname, 'helpers.ts')
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
const { hasUrlError, hasRecoveryParams } = mod.exports

const params = (search, hash = '') => [new URLSearchParams(search), new URLSearchParams(hash)]

// ── hasUrlError ────────────────────────────────────────────────────────

test('an error query param is detected', () => {
  const [search, hash] = params('error=access_denied')
  assert.equal(hasUrlError(search, hash), true)
})

test('an error hash param is detected', () => {
  const [search, hash] = params('', 'error=access_denied')
  assert.equal(hasUrlError(search, hash), true)
})

test('no error params returns false', () => {
  const [search, hash] = params('type=recovery')
  assert.equal(hasUrlError(search, hash), false)
})

// ── hasRecoveryParams: recovery (unchanged) ──────────────────────────────

test('a PKCE code param is a valid recovery param', () => {
  const [search, hash] = params('code=abc123')
  assert.equal(hasRecoveryParams(search, hash), true)
})

test('type=recovery in the query string is a valid recovery param', () => {
  const [search, hash] = params('type=recovery')
  assert.equal(hasRecoveryParams(search, hash), true)
})

test('an implicit-flow access_token hash is a valid recovery param', () => {
  const [search, hash] = params('', 'access_token=xyz&type=recovery')
  assert.equal(hasRecoveryParams(search, hash), true)
})

test('type=recovery in the hash is a valid recovery param', () => {
  const [search, hash] = params('', 'type=recovery')
  assert.equal(hasRecoveryParams(search, hash), true)
})

test('no recognized params returns false', () => {
  const [search, hash] = params('foo=bar')
  assert.equal(hasRecoveryParams(search, hash), false)
})

// ── hasRecoveryParams: invite (new) ───────────────────────────────────────

test('type=invite in the query string is now a valid recovery param', () => {
  const [search, hash] = params('type=invite')
  assert.equal(hasRecoveryParams(search, hash), true)
})

test('type=invite in the hash alone is NOT accepted (invite arrives via query string only)', () => {
  const [search, hash] = params('', 'type=invite')
  assert.equal(hasRecoveryParams(search, hash), false)
})
