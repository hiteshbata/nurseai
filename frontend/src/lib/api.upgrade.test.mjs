// Focused test for isUpgradeRequiredError() in api.ts (429 session-quota fix).
//
// No unit-test runner exists in this project (only Playwright e2e), and
// api.ts imports axios/@sentry/nextjs/react/react-hot-toast/@/lib/supabase --
// none resolvable by plain Node. Rather than add a test framework or
// duplicate the logic, this transpiles the real api.ts source (via the
// `typescript` package already in devDependencies) and runs it in a small
// sandbox with those imports stubbed, then exercises the real, exported
// isUpgradeRequiredError() with Node's built-in test runner.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Module from 'node:module'
import vm from 'node:vm'
import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

const apiPath = path.join(import.meta.dirname, 'api.ts')
const source = fs.readFileSync(apiPath, 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  },
})

const stubAxios = {
  create: () => ({
    interceptors: { request: { use: () => {} }, response: { use: () => {} } },
    get: () => {},
  }),
}

const mod = new Module(apiPath)
mod.filename = apiPath
mod.paths = Module._nodeModulePaths(path.dirname(apiPath))
const originalResolve = Module._resolveFilename
Module._resolveFilename = function (request, ...rest) {
  if (request === 'axios' || request === '@sentry/nextjs' || request === 'react' ||
      request === 'react-hot-toast' || request === '@/lib/supabase' || request === './plans') {
    return request
  }
  return originalResolve.call(this, request, ...rest)
}
mod.require = (request) => {
  switch (request) {
    case 'axios': return stubAxios
    case '@sentry/nextjs': return { captureException: () => {} }
    case 'react': return { createElement: () => {} }
    case 'react-hot-toast': return { default: { error: () => {} } }
    case '@/lib/supabase': return { supabase: {}, signOut: async () => {} }
    case './plans': return { FALLBACK_PLANS: [] }
    default: return originalResolve ? require(request) : undefined
  }
}

vm.runInThisContext(Module.wrap(outputText))(
  mod.exports, mod.require, mod, mod.filename, path.dirname(apiPath)
)
Module._resolveFilename = originalResolve

const { isUpgradeRequiredError } = mod.exports

function errorWith(status, data) {
  return { response: { status, data } }
}

test('403 with upgrade_required=true -> true', () => {
  assert.equal(isUpgradeRequiredError(errorWith(403, { detail: { upgrade_required: true } })), true)
})

test('429 with upgrade_required=true -> true', () => {
  assert.equal(isUpgradeRequiredError(errorWith(429, { detail: { upgrade_required: true, error: 'session_limit_reached' } })), true)
})

test('429 without upgrade_required -> false', () => {
  assert.equal(isUpgradeRequiredError(errorWith(429, { detail: { error: 'session_limit_reached', upgrade_required: false } })), false)
  assert.equal(isUpgradeRequiredError(errorWith(429, { detail: { error: 'session_limit_reached' } })), false)
})

test('normal non-upgrade errors -> false', () => {
  assert.equal(isUpgradeRequiredError(errorWith(500, { detail: 'internal error' })), false)
  assert.equal(isUpgradeRequiredError(errorWith(404, undefined)), false)
  assert.equal(isUpgradeRequiredError(new Error('network error')), false)
})
