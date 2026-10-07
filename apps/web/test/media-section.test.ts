import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/media-section'
import type { MediaItem, OwnerMediaItem } from '../src/owner-api'

type Section = HTMLElement & { personId: string; media: MediaItem[]; isOwner: boolean; confirm: (text: string) => boolean; updateComplete: Promise<boolean> }
const settle = async (element: Section) => { for (let index = 0; index < 5; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const root = (section: Section) => section.shadowRoot!
const buttonIn = (element: ParentNode, text: string) => [...element.querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement | undefined

const PHOTO: OwnerMediaItem = { id: 'm1', original_filename: 'anna.jpg', media_type: 'image/jpeg', caption: 'Свадьба', date_label: '1950', file_url: '/api/v1/media/m1/file', preview_url: '/api/v1/media/m1/preview', is_published: true, is_portrait: false }
const PDF: OwnerMediaItem = { id: 'm2', original_filename: 'doc.pdf', media_type: 'application/pdf', caption: null, date_label: null, file_url: '/api/v1/media/m2/file', preview_url: null, is_published: true, is_portrait: false }
const HIDDEN: OwnerMediaItem = { ...PHOTO, id: 'm3', original_filename: 'hidden.jpg', is_published: false }

function ownerApi(items: OwnerMediaItem[] = [PHOTO, PDF, HIDDEN]) {
  return vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/media') && !init) return Promise.resolve(new Response(JSON.stringify(items)))
    if (init?.method === 'DELETE') return Promise.resolve(new Response(null, { status: 204 }))
    if (init?.method === 'PUT') return Promise.resolve(new Response(JSON.stringify({ portrait_media_id: 'm1' })))
    return Promise.resolve(new Response(JSON.stringify(PHOTO)))
  })
}
async function render(options: { isOwner?: boolean; media?: MediaItem[]; fetchMock?: ReturnType<typeof vi.fn> } = {}) {
  const fetchMock = options.fetchMock ?? ownerApi()
  vi.stubGlobal('fetch', fetchMock)
  const section = document.createElement('cats-media-section') as Section
  section.personId = 'p1'
  section.media = options.media ?? []
  section.isOwner = options.isOwner ?? false
  section.confirm = vi.fn(() => true)
  document.body.append(section)
  await settle(section)
  return { section, fetchMock }
}
const tile = (section: Section, id: string) => root(section).querySelector(`.tile[data-media-id="${id}"]`) as HTMLElement
const body = (fetchMock: ReturnType<typeof vi.fn>, method: string) => JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === method)![1].body))

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-media-section', () => {
  it('shows guests photo and document tiles with captions', async () => {
    const { section, fetchMock } = await render({ media: [PHOTO, { ...PDF, caption: undefined, date_label: undefined, preview_url: undefined }] })

    expect(fetchMock).not.toHaveBeenCalled()
    expect(tile(section, 'm1').querySelector('a[target="_blank"]')?.getAttribute('href')).toBe('/api/v1/media/m1/file')
    expect(tile(section, 'm1').querySelector('img')?.getAttribute('src')).toBe('/api/v1/media/m1/preview')
    expect(tile(section, 'm1').querySelector('.caption')?.textContent).toBe('Свадьба')
    expect(tile(section, 'm1').querySelector('.date')?.textContent).toBe('1950')
    expect(tile(section, 'm2').querySelector('.doc-icon')).not.toBeNull()
    expect(tile(section, 'm2').textContent).toContain('doc.pdf')
    expect(buttonIn(root(section), 'Загрузить файлы')).toBeUndefined()
  })

  it('shows the empty state to guests', async () => {
    const { section } = await render()

    expect(root(section).querySelector('.empty')?.textContent).toBe('Фото и документы пока не добавлены')
  })

  it('lets the owner upload several files and shows each result', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const name = (init.body as FormData).get('file') as File
        return Promise.resolve(name.name === 'bad.exe'
          ? new Response(JSON.stringify({ detail: 'Разрешены JPEG, PNG и PDF.' }), { status: 422 })
          : new Response(JSON.stringify(PHOTO), { status: 201 }))
      }
      return Promise.resolve(new Response(JSON.stringify([PHOTO])))
    })
    const { section } = await render({ isOwner: true, fetchMock })
    const changed = vi.fn()
    section.addEventListener('person-changed', changed)
    const input = root(section).querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(true)
    Object.defineProperty(input, 'files', { value: [new File(['x'], 'anna.jpg', { type: 'image/jpeg' }), new File(['x'], 'bad.exe')] })

    input.dispatchEvent(new Event('change'))
    await settle(section)

    expect([...root(section).querySelectorAll('.uploads li')].map((item) => item.textContent?.trim())).toEqual(['anna.jpg: готово', 'bad.exe: Разрешены JPEG, PNG и PDF.'])
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2)
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('marks hidden files and offers a portrait only for visible photos', async () => {
    const { section } = await render({ isOwner: true })

    expect(tile(section, 'm3').classList.contains('hidden')).toBe(true)
    expect(tile(section, 'm3').textContent).toContain('скрыт')
    expect(buttonIn(tile(section, 'm1'), 'Сделать портретом')).toBeDefined()
    expect(buttonIn(tile(section, 'm2'), 'Сделать портретом')).toBeUndefined()
    expect(buttonIn(tile(section, 'm3'), 'Сделать портретом')).toBeUndefined()
    expect(buttonIn(tile(section, 'm3'), 'Показать')).toBeDefined()
  })

  it('makes a portrait, hides a file and edits a caption', async () => {
    const { section, fetchMock } = await render({ isOwner: true })

    buttonIn(tile(section, 'm1'), 'Сделать портретом')!.click()
    await settle(section)
    expect(body(fetchMock, 'PUT')).toEqual({ media_id: 'm1' })

    buttonIn(tile(section, 'm2'), 'Скрыть')!.click()
    await settle(section)
    expect(body(fetchMock, 'PATCH')).toEqual({ is_published: false })

    fetchMock.mockClear()
    buttonIn(tile(section, 'm1'), 'Изменить подпись')!.click()
    await settle(section)
    const form = tile(section, 'm1')
    const caption = form.querySelector('input[name="caption"]') as HTMLInputElement
    const date = form.querySelector('input[name="date_label"]') as HTMLInputElement
    expect(caption.value).toBe('Свадьба')
    caption.value = 'Венчание'
    caption.dispatchEvent(new Event('input'))
    date.value = '1951'
    date.dispatchEvent(new Event('input'))
    buttonIn(form, 'Сохранить')!.click()
    await settle(section)
    expect(body(fetchMock, 'PATCH')).toEqual({ caption: 'Венчание', date_label: '1951' })
  })

  it('removes a portrait mark', async () => {
    const { section, fetchMock } = await render({ isOwner: true, fetchMock: ownerApi([{ ...PHOTO, is_portrait: true }]) })

    expect(tile(section, 'm1').textContent).toContain('Портрет')
    buttonIn(tile(section, 'm1'), 'Убрать портрет')!.click()
    await settle(section)

    expect(body(fetchMock, 'PUT')).toEqual({ media_id: null })
  })

  it('deletes only after confirmation', async () => {
    const { section, fetchMock } = await render({ isOwner: true })
    ;(section.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false)

    buttonIn(tile(section, 'm2'), 'Удалить')!.click()
    await settle(section)
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)

    buttonIn(tile(section, 'm2'), 'Удалить')!.click()
    await settle(section)
    expect(section.confirm).toHaveBeenLastCalledWith('Удалить файл «doc.pdf»? Он исчезнет с сайта.')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/media/m2', { method: 'DELETE' })
  })
})
