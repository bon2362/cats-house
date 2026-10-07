import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'

it('asks search engines not to index the site', () => {
  expect(readFileSync('index.html', 'utf8')).toContain('<meta name="robots" content="noindex, nofollow" />')
})
