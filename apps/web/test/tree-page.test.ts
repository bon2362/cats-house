import { expect, it, vi } from 'vitest'

import '../src/pages/tree-page'

it('loads a mixed tree and switches its mode', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      people: [{ id: 'anna', display_name: 'Анна' }, { id: 'boris', display_name: 'Борис' }],
      links: [{ parent_id: 'anna', child_id: 'boris' }],
    }),
  })
  vi.stubGlobal('fetch', fetchMock)
  const element = document.createElement('cats-tree-page') as HTMLElement & { rootId: string }
  element.rootId = 'anna'
  document.body.append(element)
  await new Promise((resolve) => setTimeout(resolve, 0))
  await (element as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=mixed&depth=3')
  expect(element.shadowRoot?.textContent).toContain('Анна → Борис')
  ;(element.shadowRoot?.querySelector('button') as HTMLButtonElement).click()
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/tree/anna?mode=ancestors&depth=3')
})
