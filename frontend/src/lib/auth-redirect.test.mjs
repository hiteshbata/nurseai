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
const { sanitizeNext } = mod.exports

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
