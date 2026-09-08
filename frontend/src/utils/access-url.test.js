import assert from 'node:assert/strict'
import test from 'node:test'

import { buildDirectUrl } from './access-url.js'

test('builds direct URLs at the container root path', () => {
  assert.equal(
    buildDirectUrl('111.230.226.178', { port: 5701, ql_base_url: '/ql1/' }),
    'http://111.230.226.178:5701/',
  )
  assert.equal(
    buildDirectUrl('111.230.107.206', { port: 5701, ql_base_url: '/' }),
    'http://111.230.107.206:5701/',
  )
  assert.equal(
    buildDirectUrl('2001:db8::1', { port: 5702, ql_base_url: '/ql2/' }),
    'http://[2001:db8::1]:5702/',
  )
})
