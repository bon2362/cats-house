export type Qualifier = 'exact' | 'about' | 'before' | 'after' | 'between'
export type DatePoint = { year: number; month: number | null; day: number | null }
export type DateValue = DatePoint & { qualifier: Qualifier; end: DatePoint | null }
export type LifeEventView = { date: DateValue | null; date_text: string | null; place: string | null }
export type EditablePerson = {
  id: string; display_name: string; is_archived: boolean
  surname: string | null; given_name: string | null; patronymic: string | null; birth_surname: string | null
  sex: 'M' | 'F' | null; birth: LifeEventView | null; death: LifeEventView & { status: 'unknown' | 'deceased' }
}
export type LifeEventInput = { date: DateValue | null; place: string | null; date_text_keep: boolean }
export type PersonEditPayload = {
  surname: string | null; given_name: string | null; patronymic: string | null; birth_surname: string | null
  sex: 'M' | 'F' | null; birth: LifeEventInput | null; death: LifeEventInput & { status: 'unknown' | 'deceased' }
}
export type OwnerSearchResult = { id: string; display_name: string; years: string | null; is_archived: boolean }
export type Relation = 'child' | 'parent' | 'spouse' | 'sibling'
export type PersonRef = { id: string; display_name: string }
export type FamilyOverview = { parents: PersonRef[]; unions: { union_id: string; partner: PersonRef | null }[]; can_add_parent: boolean; can_add_sibling: boolean }
export type AddRelativePayload = { relation: Relation; person: PersonEditPayload | null; existing_id: string | null; union_id: string | null }
export type AddRelativeResult = { relation: Relation; created: boolean; person: EditablePerson }
export type ApiResult<T> = { ok: true; value: T } | { ok: false; message: string }

const UNAVAILABLE = 'Сервер недоступен. Попробуйте позже.'

async function request<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response
  try {
    response = await (init ? fetch(url, init) : fetch(url))
  } catch {
    return { ok: false, message: UNAVAILABLE }
  }
  if (response.status === 401) return { ok: false, message: 'Войдите как владелец, чтобы изменять данные.' }
  if (response.status === 404) return { ok: false, message: 'Человек не найден.' }
  if (response.status === 422) {
    const detail = await response.json().then((data) => data?.detail, () => null)
    return { ok: false, message: typeof detail === 'string' ? detail : 'Проверьте заполнение полей.' }
  }
  if (!response.ok) return { ok: false, message: 'Не удалось сохранить. Попробуйте ещё раз.' }
  const text = await response.text()
  return { ok: true, value: (text ? JSON.parse(text) : null) as T }
}

const json = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const fetchEditablePerson = (id: string) => request<EditablePerson>(`/api/v1/admin/people/${id}`)
export const savePerson = (id: string, payload: PersonEditPayload) => request<EditablePerson>(`/api/v1/admin/people/${id}`, json('PATCH', payload))
export const archivePerson = (id: string) => request<null>(`/api/v1/admin/people/${id}/archive`, { method: 'POST' })
export const restorePerson = (id: string) => request<null>(`/api/v1/admin/people/${id}/restore`, { method: 'POST' })
export const searchOwnerPeople = (query: string) => request<OwnerSearchResult[]>(`/api/v1/admin/people?query=${encodeURIComponent(query)}`)
export const fetchFamily = (id: string) => request<FamilyOverview>(`/api/v1/admin/people/${id}/family`)
export const findSimilarPeople = (names: { given_name: string; surname: string; birth_surname: string }) => request<OwnerSearchResult[]>(`/api/v1/admin/people/similar?${new URLSearchParams(names)}`)
export const addRelative = (id: string, payload: AddRelativePayload) => request<AddRelativeResult>(`/api/v1/admin/people/${id}/relatives`, json('POST', payload))
