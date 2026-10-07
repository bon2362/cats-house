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
    media: [{ id: 'media-id', original_filename: 'family-photo.jpg', media_type: 'image/jpeg', file_url: '/api/v1/media/media-id/file', preview_url: '/api/v1/media/media-id/preview' }],
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
  const gallery = element.shadowRoot?.querySelector('#media cats-media-section') as HTMLElement & { media: { id: string }[]; isOwner: boolean }
  expect(gallery.media.map((item) => item.id)).toEqual(['media-id'])
  expect(gallery.isOwner).toBe(false)
  const biography = element.shadowRoot?.querySelector('#biography cats-biography-section') as HTMLElement & { biography: string | null; personId: string }
  expect([biography.personId, biography.biography]).toEqual(['anna-id', 'Семейная заметка'])
})

const person = {
  id: 'p1', display_name: 'Анна Иванова', biography: null, events: [], parents: [], children: [], partners: [], media: [],
}
afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('shows «Изменить» only to the owner and opens the editor in place', async () => {
  vi.stubGlobal('fetch', ownerApi(JSON.stringify({ id: person.id, display_name: person.display_name, is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } })))
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
  vi.stubGlobal('fetch', ownerApi(JSON.stringify({ id: person.id, display_name: person.display_name, is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } })))
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
  vi.stubGlobal('fetch', ownerApi(JSON.stringify({ id: 'p1', display_name: 'Анна', is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } })))
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
  expect((element.shadowRoot?.querySelector('cats-biography-section') as HTMLElement).shadowRoot?.textContent).toContain('Биография пока не написана')
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

it('offers adding relatives only to the owner', async () => {
  vi.stubGlobal('fetch', ownerApi('{}'))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  document.body.append(card)
  await card.updateComplete
  expect(card.shadowRoot!.querySelector('cats-relative-section')).toBeNull()

  card.isOwner = true
  await card.updateComplete

  expect((card.shadowRoot!.querySelector('#family cats-relative-section') as HTMLElement & { personId: string }).personId).toBe('p1')
})

it('lists siblings instead of the placeholder', async () => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, siblings: [{ id: 's1', display_name: 'Ольга' }] }
  document.body.append(card)
  await card.updateComplete

  const column = [...card.shadowRoot!.querySelectorAll('.family-columns > div')].find((item) => item.querySelector('h3')?.textContent === 'Братья и сёстры')!
  expect(column.querySelector('a')?.getAttribute('href')).toBe('/people/s1')
  expect(column.textContent).not.toContain('пока не указаны')
})

it('shows the «Связи» block above «Добавить родственника» for the owner only', async () => {
  vi.stubGlobal('fetch', ownerApi(JSON.stringify({ parents: [], unions: [], children_without_union: [], can_add_parent: true, can_add_sibling: false })))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  document.body.append(card)
  await card.updateComplete

  const blocks = [...card.shadowRoot!.querySelectorAll('#family cats-family-editor, #family cats-relative-section')].map((item) => item.tagName.toLowerCase())
  expect(blocks).toEqual(['cats-family-editor', 'cats-relative-section'])
})

/** Owner page requests: the family overview for «Связи», everything else gets `body`. */
function ownerApi(body: string) {
  const family = JSON.stringify({ parents: [], unions: [], children_without_union: [], can_add_parent: true, can_add_sibling: false })
  return vi.fn((url: string) => Promise.resolve(new Response(String(url).endsWith('/family') ? family : body)))
}

it('shows the portrait instead of the monogram and keeps the biography out of the header', async () => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, biography: 'Длинная история', portrait: { id: 'm1', preview_url: '/api/v1/media/m1/preview', file_url: '/api/v1/media/m1/file' } }
  document.body.append(card)
  await card.updateComplete

  const hero = card.shadowRoot!.querySelector('.hero')!
  expect(hero.querySelector('img.portrait')?.getAttribute('src')).toBe('/api/v1/media/m1/preview')
  expect(hero.querySelector('.monogram')).toBeNull()
  expect(hero.textContent).not.toContain('Длинная история')
})

it('gives the owner editable biography and media sections', async () => {
  vi.stubGlobal('fetch', ownerApi('[]'))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  document.body.append(card)
  await card.updateComplete

  for (const selector of ['#biography cats-biography-section', '#media cats-media-section']) {
    const section = card.shadowRoot!.querySelector(selector) as HTMLElement & { personId: string; isOwner: boolean }
    expect([section.personId, section.isOwner]).toEqual(['p1', true])
  }
})
