import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/biography-section'

type Section = HTMLElement & { personId: string; biography: string | null | undefined; isOwner: boolean; updateComplete: Promise<boolean> }
const settle = async (element: Section) => { for (let index = 0; index < 4; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const root = (section: Section) => section.shadowRoot!
const button = (section: Section, text: string) => [...root(section).querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement | undefined

async function render(options: { biography?: string | null; isOwner?: boolean; fetchMock?: ReturnType<typeof vi.fn> } = {}) {
  const fetchMock = options.fetchMock ?? vi.fn().mockResolvedValue(new Response(JSON.stringify({ biography: 'Новый' })))
  vi.stubGlobal('fetch', fetchMock)
  const section = document.createElement('cats-biography-section') as Section
  section.personId = 'p1'
  if ('biography' in options) section.biography = options.biography
  section.isOwner = options.isOwner ?? false
  document.body.append(section)
  await settle(section)
  return { section, fetchMock }
}
const type = async (section: Section, text: string) => {
  const area = root(section).querySelector('textarea[name="biography"]') as HTMLTextAreaElement
  area.value = text
  area.dispatchEvent(new Event('input'))
  await settle(section)
}

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-biography-section', () => {
  it('shows paragraphs to guests and no edit button', async () => {
    const { section } = await render({ biography: 'Первый абзац.\n\nВторой абзац.' })

    expect([...root(section).querySelectorAll('p.bio')].map((item) => item.textContent)).toEqual(['Первый абзац.', 'Второй абзац.'])
    expect(button(section, 'Изменить')).toBeUndefined()
  })

  it('shows the empty state', async () => {
    const { section } = await render({ biography: null })

    expect(root(section).querySelector('.empty')?.textContent).toBe('Биография пока не написана')
  })

  it('lets the owner edit, counts characters and reports the change', async () => {
    const { section, fetchMock } = await render({ biography: 'Старый', isOwner: true })
    const changed = vi.fn()
    section.addEventListener('person-changed', changed)

    button(section, 'Изменить')!.click()
    await settle(section)
    expect((root(section).querySelector('textarea[name="biography"]') as HTMLTextAreaElement).value).toBe('Старый')
    await type(section, 'Новый')
    expect(root(section).querySelector('.counter')?.textContent).toBe('5 из 20000')
    button(section, 'Сохранить')!.click()
    await settle(section)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1/biography', expect.objectContaining({ method: 'PATCH' }))
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ biography: 'Новый' })
    expect(root(section).querySelector('p.bio')?.textContent).toBe('Новый')
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('keeps the draft and shows the reason when saving fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Биография не может быть длиннее 20000 символов.' }), { status: 422 }))
    const { section } = await render({ biography: null, isOwner: true, fetchMock })

    button(section, 'Изменить')!.click()
    await settle(section)
    await type(section, 'Черновик')
    button(section, 'Сохранить')!.click()
    await settle(section)

    expect(root(section).querySelector('[role="alert"]')?.textContent).toContain('20000')
    expect((root(section).querySelector('textarea[name="biography"]') as HTMLTextAreaElement).value).toBe('Черновик')
  })

  it('cancels without a request', async () => {
    const { section, fetchMock } = await render({ biography: 'Текст', isOwner: true })

    button(section, 'Изменить')!.click()
    await settle(section)
    await type(section, 'Другое')
    button(section, 'Отмена')!.click()
    await settle(section)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(root(section).querySelector('p.bio')?.textContent).toBe('Текст')
  })

  it('loads the biography itself when the page does not pass it (hidden person)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'p1', biography: 'Из формы' })))
    const { section } = await render({ isOwner: true, fetchMock })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1')
    expect(root(section).querySelector('p.bio')?.textContent).toBe('Из формы')
  })
})
