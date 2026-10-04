import { expect, it } from 'vitest'

import '../src/pages/person-card'

it('renders a person, their events, and family links', async () => {
  const element = document.createElement('cats-person-card') as HTMLElement & { person: unknown }
  element.person = {
    display_name: 'Анна Иванова',
    biography: 'Семейная заметка',
    events: [{ event_type: 'BIRT', date_text: '1900' }],
    parents: [{ id: 'parent-id', display_name: 'Иван Иванов' }],
    children: [],
    partners: [{ id: 'partner-id', display_name: 'Пётр Петров' }],
    media: [{ id: 'media-id', original_filename: 'family-photo.jpg', url: 'https://media.example.test/family-photo.jpg' }],
  }
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Анна Иванова')
  expect(element.shadowRoot?.textContent).toContain('1900')
  expect(element.shadowRoot?.textContent).toContain('Иван Иванов')
  expect(element.shadowRoot?.querySelector('a[href="/people/parent-id"]')).not.toBeNull()
  expect(element.shadowRoot?.querySelector('a[href="https://media.example.test/family-photo.jpg"]')).not.toBeNull()
})
