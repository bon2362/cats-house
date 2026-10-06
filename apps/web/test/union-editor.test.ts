import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/union-editor'
import type { UnionDetails } from '../src/owner-api'

type Editor = HTMLElement & { union: UnionDetails; updateComplete: Promise<boolean> }
const settle = async (element: Editor) => { for (let index = 0; index < 3; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const UNION: UnionDetails = { union_id: 'u1', partner: { id: 'v', display_name: 'Виктор' }, marriage: { date: { qualifier: 'exact', year: 1975, month: null, day: null, end: null }, date_text: '1975', place: null }, divorce: null, children: [] }

async function render(union = UNION, response: Response = new Response(JSON.stringify({ union_id: 'u1', marriage: null, divorce: { date: null, date_text: null } }))) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  const editor = document.createElement('cats-union-editor') as Editor
  editor.union = union
  document.body.append(editor)
  await settle(editor)
  return { editor, fetchMock }
}
const button = (editor: Editor, text: string) => [...editor.shadowRoot!.querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement
const body = (fetchMock: ReturnType<typeof vi.fn>) => JSON.parse(String(fetchMock.mock.calls[0][1].body))

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('marks a divorce without a date and keeps the marriage date', async () => {
  const { editor, fetchMock } = await render()
  const saved = vi.fn()
  editor.addEventListener('union-saved', saved)
  expect(editor.shadowRoot!.querySelector('cats-date-input[data-kind="divorce"]')).toBeNull()

  const divorced = editor.shadowRoot!.querySelector('input[name="divorced"]') as HTMLInputElement
  divorced.checked = true
  divorced.dispatchEvent(new Event('change'))
  await settle(editor)
  expect(editor.shadowRoot!.querySelector('cats-date-input[data-kind="divorce"]')).not.toBeNull()
  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/unions/u1', expect.objectContaining({ method: 'PATCH' }))
  expect(body(fetchMock)).toEqual({ marriage: { date: UNION.marriage!.date, place: null }, divorced: true, divorce_date: null })
  expect(saved).toHaveBeenCalledTimes(1)
})

it('sends no marriage when neither date nor place is filled', async () => {
  const { editor, fetchMock } = await render({ ...UNION, marriage: null })

  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(body(fetchMock)).toEqual({ marriage: null, divorced: false, divorce_date: null })
})

it('shows the server reason and cancels without saving', async () => {
  const { editor } = await render(UNION, new Response(JSON.stringify({ detail: 'У союза несколько событий брака — исправьте их отдельно.' }), { status: 422 }))
  const cancelled = vi.fn()
  editor.addEventListener('union-cancel', cancelled)

  button(editor, 'Сохранить').click()
  await settle(editor)
  expect(editor.shadowRoot!.querySelector('[role="alert"]')?.textContent).toContain('несколько событий брака')

  button(editor, 'Отмена').click()
  expect(cancelled).toHaveBeenCalledTimes(1)
})

it('keeps an unparsed archive marriage date when only the divorce is marked', async () => {
  const legacy = { ...UNION, marriage: { date: null, date_text: 'весной 1975', place: null } }
  const { editor, fetchMock } = await render(legacy)

  expect(editor.shadowRoot!.textContent).toContain('весной 1975')
  const divorced = editor.shadowRoot!.querySelector('input[name="divorced"]') as HTMLInputElement
  divorced.checked = true
  divorced.dispatchEvent(new Event('change'))
  await settle(editor)
  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(body(fetchMock)).toEqual({ marriage: { date: null, place: null, date_text_keep: true }, divorced: true, divorce_date: null })
})

it('keeps an unparsed archive divorce date when the marriage is edited', async () => {
  const { editor, fetchMock } = await render({ ...UNION, divorce: { date: null, date_text: 'после войны' } })

  expect(editor.shadowRoot!.textContent).toContain('после войны')
  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(body(fetchMock)).toEqual({ marriage: { date: UNION.marriage!.date, place: null }, divorced: true, divorce_date: null, divorce_date_text_keep: true })
})

it('refuses a half-typed marriage date instead of erasing the stored one', async () => {
  const { editor, fetchMock } = await render()
  const dateInput = editor.shadowRoot!.querySelector('cats-date-input[data-kind="marriage"]') as HTMLElement & { updateComplete: Promise<boolean> }
  const year = dateInput.shadowRoot!.querySelector('input[name$="year"]') as HTMLInputElement
  year.value = ''
  year.dispatchEvent(new Event('input'))
  const day = dateInput.shadowRoot!.querySelector('input[name$="day"]') as HTMLInputElement
  day.value = '12'
  day.dispatchEvent(new Event('input'))
  await settle(editor)

  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(editor.shadowRoot!.querySelector('[role="alert"]')?.textContent).toContain('Укажите год.')
  expect(fetchMock).not.toHaveBeenCalled()
})
