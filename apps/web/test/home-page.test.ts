import { expect, it } from 'vitest'

import '../src/pages/home-page'

it('renders the archive catalogue grouped by surname initial', async () => {
  const element = document.createElement('cats-house-home') as HTMLElement & { people: unknown }
  element.people = [
    { id: '1', display_name: 'Иванов Иван Петрович', years: '1901 – 1975' },
    { id: '2', display_name: 'Кошкина Анна Ивановна', years: 'р. 1951' },
  ]
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Выберите человека')
  expect(element.shadowRoot?.textContent).toContain('И')
  expect(element.shadowRoot?.textContent).toContain('К')
  expect(element.shadowRoot?.querySelector('a[href="/tree?person=1"]')).not.toBeNull()
})

it('shows a skeleton instead of the empty message while the catalogue loads', async () => {
  const element = document.createElement('cats-house-home') as HTMLElement & { people: unknown; loading: boolean; updateComplete: Promise<void> }
  element.loading = true
  document.body.append(element)
  await element.updateComplete

  expect(element.shadowRoot?.textContent).not.toContain('пока нет людей')
  expect(element.shadowRoot?.textContent).toContain('Загружаем архив')
  expect(element.shadowRoot?.querySelectorAll('.skeleton-list .person').length).toBeGreaterThan(0)
  expect(element.shadowRoot?.querySelector('main')?.getAttribute('aria-busy')).toBe('true')

  element.loading = false
  await element.updateComplete
  expect(element.shadowRoot?.querySelector('.skeleton-list')).toBeNull()
  expect(element.shadowRoot?.textContent).toContain('пока нет людей')
})
