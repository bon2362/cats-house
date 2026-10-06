import type { DatePoint, DateValue } from './owner-api'

export const MONTHS_NOMINATIVE = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const MONTHS_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const MONTHS_INSTRUMENTAL = ['январём', 'февралём', 'мартом', 'апрелем', 'маем', 'июнем', 'июлем', 'августом', 'сентябрём', 'октябрём', 'ноябрём', 'декабрём']
const PREFIX = { exact: '', about: 'ок. ', before: 'до ', after: 'после ' } as const

function pointRu(point: DatePoint, months: string[]): string {
  if (point.month === null) return String(point.year)
  if (point.day !== null) return `${point.day} ${MONTHS_GENITIVE[point.month - 1]} ${point.year}`
  return `${months[point.month - 1]} ${point.year}`
}

/** Same rules as the API's format_date_ru, for the preview under the date input. */
export function formatDateValueRu(value: DateValue): string {
  if (value.qualifier === 'between') return `между ${pointRu(value, MONTHS_INSTRUMENTAL)} и ${value.end ? pointRu(value.end, MONTHS_INSTRUMENTAL) : '…'}`
  return PREFIX[value.qualifier] + pointRu(value, value.qualifier === 'exact' ? MONTHS_NOMINATIVE : MONTHS_GENITIVE)
}
