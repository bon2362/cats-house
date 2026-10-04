// @vitest-environment node

import { describe, expect, it } from 'vitest'

import config from '../vite.config'

describe('Vite development server', () => {
  it('proxies browser API requests to the local API service', () => {
    expect(config.server?.proxy?.['/api']).toMatchObject({
      target: 'http://localhost:8000',
      changeOrigin: true,
    })
  })
})
