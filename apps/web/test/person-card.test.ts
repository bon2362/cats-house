import { expect, it } from 'vitest'

import '../src/pages/person-card'

it('renders a person and their events', async () => {
  const element = document.createElement('cats-person-card') as HTMLElement & { person: unknown }
  element.person = {
    display_name: 'Анна Иванова',
    biography: 'Семейная заметка',
    events: [{ event_type: 'BIRT', date_text: '1900' }],
  }
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Анна Иванова')
  expect(element.shadowRoot?.textContent).toContain('1900')
})
