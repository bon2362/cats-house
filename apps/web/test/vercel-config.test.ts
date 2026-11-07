// @vitest-environment node

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const config = JSON.parse(readFileSync(resolve(import.meta.dirname, '..', 'vercel.json'), 'utf8'))

describe('Vercel production delivery', () => {
  it('keeps API calls on the canonical site origin and serves SPA routes', () => {
    expect(config.outputDirectory).toBe('dist')
    expect(config.rewrites).toEqual([
      { source: '/api/:path*', destination: 'https://api.catshouse.online/api/:path*' },
      { source: '/(.*)', destination: '/index.html' },
    ])
  })

  it('adds the privacy and framing safeguards to static responses', () => {
    expect(config.headers).toEqual([{
      source: '/(.*)',
      headers: [
        { key: 'X-Robots-Tag', value: 'noindex, nofollow, noarchive' },
        { key: 'X-Frame-Options', value: 'DENY' },
        { key: 'Referrer-Policy', value: 'same-origin' },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
      ],
    }])
  })
})
