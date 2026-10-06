import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/components/date-input'
import { formatDateValueRu } from '../src/date-format'
import type { DateValue } from '../src/owner-api'

type DateInput = HTMLElement & { value: DateValue | null; updateComplete: Promise<boolean> }
const point = (year: number, month: number | null = null, day: number | null = null) => ({ year, month, day })

async function render(value: DateValue | null) {
  const element = document.createElement('cats-date-input') as DateInput
  element.value = value
  document.body.append(element)
  await element.updateComplete
  return element
}
function change(element: DateInput, name: string, value: string) {
  const control = element.shadowRoot!.querySelector(`[name="${name}"]`) as HTMLInputElement | HTMLSelectElement
  control.value = value
  control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'))
}

afterEach(() => document.body.replaceChildren())

describe('formatDateValueRu', () => {
  it.each([
    [{ qualifier: 'exact', ...point(1926, 4, 6), end: null }, '6 апреля 1926'],
    [{ qualifier: 'exact', ...point(2004, 3), end: null }, 'март 2004'],
    [{ qualifier: 'about', ...point(1900), end: null }, 'ок. 1900'],
    [{ qualifier: 'before', ...point(1944, 3), end: null }, 'до марта 1944'],
    [{ qualifier: 'after', ...point(1950), end: null }, 'после 1950'],
    [{ qualifier: 'between', ...point(1900, 3), end: point(1905, 5) }, 'между мартом 1900 и маем 1905'],
  ] as [DateValue, string][])('formats %j', (value, label) => {
    expect(formatDateValueRu(value)).toBe(label)
  })
})

describe('cats-date-input', () => {
  it('shows the stored value and its public label', async () => {
    const element = await render({ qualifier: 'about', ...point(1901, 4), end: null })

    expect((element.shadowRoot!.querySelector('[name="qualifier"]') as HTMLSelectElement).value).toBe('about')
    expect((element.shadowRoot!.querySelector('[name="month"]') as HTMLSelectElement).value).toBe('4')
    expect((element.shadowRoot!.querySelector('[name="year"]') as HTMLInputElement).value).toBe('1901')
    expect(element.shadowRoot!.querySelector('.preview')?.textContent).toContain('ок. апреля 1901')
  })

  it('emits a structured value as the owner types and null without a year', async () => {
    const element = await render(null)
    const changes: (DateValue | null)[] = []
    element.addEventListener('date-change', (event) => changes.push((event as CustomEvent).detail))

    change(element, 'year', '1944')
    change(element, 'month', '3')
    change(element, 'qualifier', 'before')
    change(element, 'year', '')

    expect(changes).toEqual([
      { qualifier: 'exact', year: 1944, month: null, day: null, end: null },
      { qualifier: 'exact', year: 1944, month: 3, day: null, end: null },
      { qualifier: 'before', year: 1944, month: 3, day: null, end: null },
      null,
    ])
  })

  it('asks for a second date only for a period', async () => {
    const element = await render({ qualifier: 'exact', ...point(1900), end: null })
    expect(element.shadowRoot!.querySelector('[name="end-year"]')).toBeNull()
    const changes: (DateValue | null)[] = []
    element.addEventListener('date-change', (event) => changes.push((event as CustomEvent).detail))

    change(element, 'qualifier', 'between')
    element.value = changes.at(-1)!
    await element.updateComplete
    change(element, 'end-year', '1905')

    expect(changes.at(-1)).toEqual({ qualifier: 'between', year: 1900, month: null, day: null, end: { year: 1905, month: null, day: null } })
  })
})
