import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/relative-section'

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('opens the adder for the chosen relation and reports the added person', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ parents: [], unions: [], can_add_parent: true, can_add_sibling: false }))))
  const section = document.createElement('cats-relative-section') as HTMLElement & { personId: string; updateComplete: Promise<boolean> }
  section.personId = 'p1'
  document.body.append(section)
  await section.updateComplete
  const changed = vi.fn()
  section.addEventListener('person-changed', changed)

  ;[...section.shadowRoot!.querySelectorAll('.add-relative button')].find((item) => item.textContent?.trim() === 'Супруга')!.dispatchEvent(new MouseEvent('click'))
  await section.updateComplete
  const adder = section.shadowRoot!.querySelector('cats-relative-adder') as HTMLElement & { relation: string; personId: string }
  expect([adder.relation, adder.personId]).toEqual(['spouse', 'p1'])

  adder.dispatchEvent(new CustomEvent('relative-added', { detail: { relation: 'spouse', created: true, person: { id: 'new', display_name: 'Мария Иванова' } }, bubbles: true, composed: true }))
  await section.updateComplete

  expect(section.shadowRoot!.querySelector('cats-relative-adder')).toBeNull()
  expect(section.shadowRoot!.querySelector('[role="status"] a')?.getAttribute('href')).toBe('/people/new')
  expect(changed).toHaveBeenCalledTimes(1)
})

it('closes the adder on cancel', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ parents: [], unions: [], can_add_parent: true, can_add_sibling: false }))))
  const section = document.createElement('cats-relative-section') as HTMLElement & { personId: string; updateComplete: Promise<boolean> }
  section.personId = 'p1'
  document.body.append(section)
  await section.updateComplete
  ;[...section.shadowRoot!.querySelectorAll('.add-relative button')].find((item) => item.textContent?.trim() === 'Ребёнка')!.dispatchEvent(new MouseEvent('click'))
  await section.updateComplete

  section.shadowRoot!.querySelector('cats-relative-adder')!.dispatchEvent(new CustomEvent('adder-cancel', { bubbles: true, composed: true }))
  await section.updateComplete

  expect(section.shadowRoot!.querySelector('cats-relative-adder')).toBeNull()
})
