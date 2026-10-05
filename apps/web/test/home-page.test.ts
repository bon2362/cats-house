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
