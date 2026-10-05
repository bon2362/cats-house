import { expect, it } from 'vitest'

import '../src/pages/person-card'

it('renders a profile, family, and a readable chronology', async () => {
  const element = document.createElement('cats-person-card') as HTMLElement & { person: unknown }
  element.person = {
    id: 'anna-id',
    display_name: 'Анна Иванова',
    biography: 'Семейная заметка',
    events: [
      { event_type: 'BIRT', date_text: '14 MAY 1900' },
      { event_type: 'DEAT', date_text: '1962' },
      { event_type: 'MARR', date_text: '1921' },
    ],
    parents: [{ id: 'parent-id', display_name: 'Иван Иванов' }],
    children: [],
    partners: [{ id: 'partner-id', display_name: 'Пётр Петров' }],
    media: [{ id: 'media-id', original_filename: 'family-photo.jpg', url: 'https://media.example.test/family-photo.jpg' }],
  }
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Анна Иванова')
  expect(element.shadowRoot?.textContent).toContain('Профиль человека')
  expect(element.shadowRoot?.textContent).toContain('Построить дерево')
  expect(element.shadowRoot?.textContent).toContain('Семья')
  expect(element.shadowRoot?.textContent).toContain('Родители')
  expect(element.shadowRoot?.textContent).toContain('Рождение')
  expect(element.shadowRoot?.textContent).toContain('14 мая 1900')
  expect(element.shadowRoot?.textContent).toContain('Смерть')
  expect(element.shadowRoot?.textContent).toContain('Брак')
  expect(element.shadowRoot?.textContent).toContain('Иван Иванов')
  expect(element.shadowRoot?.querySelector('a[href="/people/parent-id"]')).not.toBeNull()
  expect(element.shadowRoot?.querySelector('a[href="/tree?person=anna-id"]')).not.toBeNull()
  expect(element.shadowRoot?.querySelector('a[href="https://media.example.test/family-photo.jpg"]')).not.toBeNull()
})

it('uses clear empty states instead of empty family and event lists', async () => {
  const element = document.createElement('cats-person-card') as HTMLElement & { person: unknown }
  element.person = {
    id: 'unknown-id',
    display_name: 'Пётр',
    biography: null,
    events: [],
    parents: [],
    children: [],
    partners: [],
    media: [],
  }
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('Родители в архиве не указаны')
  expect(element.shadowRoot?.textContent).toContain('Союзы и дети в архиве не указаны')
  expect(element.shadowRoot?.textContent).toContain('Хронология пока не заполнена')
  expect(element.shadowRoot?.textContent).toContain('Биография пока не написана')
})
