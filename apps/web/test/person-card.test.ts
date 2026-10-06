import { afterEach, expect, it, vi } from 'vitest'

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

const person = {
  id: 'p1', display_name: 'Анна Иванова', biography: null, events: [], parents: [], children: [], partners: [], media: [],
}
afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('shows «Изменить» only to the owner and opens the editor in place', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: person.id, display_name: person.display_name, is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  document.body.append(card)
  await card.updateComplete
  const edit = () => [...card.shadowRoot!.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Изменить')
  expect(edit()).toBeUndefined()

  card.isOwner = true
  await card.updateComplete
  edit()!.click()
  await card.updateComplete

  expect(card.shadowRoot!.querySelector('cats-person-editor')).not.toBeNull()
})

it('opens the editor directly for the owner on ?edit=1 and reports a save', async () => {
  history.pushState({}, '', `/people/${person.id}?edit=1`)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: person.id, display_name: person.display_name, is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  const changed = vi.fn()
  card.addEventListener('person-changed', changed)
  document.body.append(card)
  await card.updateComplete

  const editor = card.shadowRoot!.querySelector('cats-person-editor')!
  editor.dispatchEvent(new CustomEvent('person-saved', { detail: {}, bubbles: true, composed: true }))
  await card.updateComplete

  expect(changed).toHaveBeenCalledTimes(1)
  expect(card.shadowRoot!.querySelector('cats-person-editor')).toBeNull()
  expect(card.shadowRoot!.textContent).toContain('Сохранено')
  history.pushState({}, '', '/')
})

it('shows the birth surname by sex', async () => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, sex: 'F', birth_surname: 'Петрова' }
  document.body.append(card)
  await card.updateComplete

  expect(card.shadowRoot!.textContent).toContain('урождённая Петрова')
})

it('closes an open editor when the owner signs out', async () => {
  history.pushState({}, '', '/people/p1?edit=1')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'p1', display_name: 'Анна', is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  document.body.append(card)
  await card.updateComplete
  expect(card.shadowRoot!.querySelector('cats-person-editor')).not.toBeNull()
  card.isOwner = false
  await card.updateComplete
  expect(card.shadowRoot!.querySelector('cats-person-editor')).toBeNull()
  history.pushState({}, '', '/')
})

it.each(['DEAT', 'DEATH'])('shows a known %s fact even without a date or place', async (event_type) => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, events: [{ event_type, date_text: null, date_label_ru: null, place: null, description: null }] }
  document.body.append(card)
  await card.updateComplete
  expect(card.shadowRoot!.querySelector('.event-name')?.textContent).toBe('Смерть')
  expect(card.shadowRoot!.querySelector('.event-date')?.textContent).toBe('Дата смерти неизвестна.')
  expect(card.shadowRoot!.querySelector('#timeline')?.textContent).not.toContain('Хронология пока не заполнена')
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

it('uses extended life details when the API provides them and omits empty events', async () => {
  const element = document.createElement('cats-person-card') as HTMLElement & { person: unknown }
  element.person = {
    id: 'extended-id',
    display_name: 'Мария Петрова',
    biography: null,
    birth_label_ru: '14 мая 1895',
    death_label_ru: '2 февраля 1962',
    birth_place: 'д. Ольховка',
    death_place: 'Калинин',
    events: [
      { event_type: 'BIRT', date_text: null },
      { event_type: 'RESI', date_label_ru: '1934', place: 'Торжок', description: 'Переезд' },
    ],
    parents: [], children: [], partners: [], media: [],
  }
  document.body.append(element)
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(element.shadowRoot?.textContent).toContain('14 мая 1895, д. Ольховка — 2 февраля 1962, Калинин')
  expect(element.shadowRoot?.textContent).toContain('Место жительства')
  expect(element.shadowRoot?.textContent).toContain('1934 · Торжок')
  expect(element.shadowRoot?.textContent).not.toContain('Рождениедата неизвестна')
})
