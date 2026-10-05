import { LitElement, css, html } from 'lit'

export type ConnectionState = 'loading' | 'ready' | 'unavailable'
export type PersonSummary = { id: string; display_name: string; years?: string | null; parents_label?: string | null; is_living?: boolean | null }
type Filter = 'all' | 'living' | 'dead'

const normalized = (value: string) => value.toLowerCase().replaceAll('ё', 'е').trim()
const familyInitial = (person: PersonSummary) => person.display_name.trim()[0]?.toUpperCase() ?? '#'
const initials = (person: PersonSummary) => person.display_name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()

export class CatsHouseHome extends LitElement {
  static properties = { connectionState: { attribute: false }, people: { attribute: false }, query: { state: true }, filter: { state: true } }
  declare connectionState: ConnectionState
  declare people: PersonSummary[]
  private declare query: string
  private declare filter: Filter

  constructor() { super(); this.connectionState = 'loading'; this.people = []; this.query = new URLSearchParams(window.location.search).get('q') ?? ''; this.filter = 'all' }

  static styles = css`
    :host { display:block; min-height:calc(100vh - 4rem); background:var(--paper,#f5f5f3); color:var(--ink,#171817); }
    main { width:min(100% - 3rem, 60.5rem); margin:0 auto; padding:4rem 0 6rem; }
    .eyebrow { color:var(--green,#24513f); font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
    h1 { margin:.9rem 0 .7rem; font-family:var(--font-serif,Georgia,serif); font-size:clamp(2.8rem,6vw,4.8rem); font-weight:400; letter-spacing:-.05em; line-height:1; }
    .lead { max-width:40rem; color:var(--text-2,#4a4c49); font-size:1.1rem; line-height:1.5; }
    .catalogue-controls { position:sticky; z-index:2; top:0; margin:2.5rem 0 1.25rem; border-bottom:1px solid var(--ink,#171817); background:var(--paper,#f5f5f3); padding:1rem 0 .85rem; }
    .catalogue-search { width:100%; height:3.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; background:var(--sheet,#fff); color:var(--ink,#171817); font:inherit; font-size:1rem; padding:0 1rem; }
    .catalogue-search:focus { border-color:var(--green,#24513f); box-shadow:0 0 0 3px var(--green-light,#e4ece7); outline:0; }
    .filters { display:flex; align-items:center; gap:.4rem; margin-top:.75rem; }
    .filter { border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); color:var(--text-2,#4a4c49); cursor:pointer; font:inherit; font-size:.8rem; font-weight:600; padding:.45rem .8rem; }
    .filter.active { border-color:var(--ink,#171817); background:var(--ink,#171817); color:#fff; }
    .count { color:var(--text-3,#6b6d69); font-size:.875rem; margin-left:.55rem; }
    .letters { display:flex; gap:.6rem; margin-left:auto; }
    .letters a { color:var(--ink,#171817); font-family:var(--font-serif,Georgia,serif); text-decoration:none; }
    .group { display:grid; grid-template-columns:5.5rem 1fr; border-bottom:1px solid var(--border,#dcdcd8); padding:1.5rem 0; scroll-margin-top:8rem; }
    .letter { font-family:var(--font-serif,Georgia,serif); font-size:2.6rem; line-height:1; }
    .person { display:grid; grid-template-columns:2.65rem minmax(0,1fr) auto; align-items:center; gap:1rem; min-height:4.1rem; padding:.55rem 0; }
    .person + .person { border-top:1px solid var(--subtle,#ececea); }
    .monogram { display:grid; width:2.65rem; height:2.65rem; place-items:center; background:var(--subtle,#ececea); color:var(--text-2,#4a4c49); font-size:.75rem; font-weight:700; }
    .name { display:block; color:var(--ink,#171817); font-weight:650; text-decoration:none; }
    .meta { color:var(--text-3,#6b6d69); font-size:.825rem; line-height:1.4; }
    .actions { display:flex; gap:.5rem; }
    .action { border:1px solid var(--border-input,#cfcfca); border-radius:3px; color:var(--ink,#171817); font-size:.8rem; font-weight:600; padding:.55rem .7rem; text-decoration:none; white-space:nowrap; }
    .action.primary { border-color:transparent; background:var(--green-light,#e4ece7); color:var(--green,#24513f); }
    .empty { color:var(--text-2,#4a4c49); padding:2.5rem 0; }
    @media (max-width:42rem) { main { width:min(100% - 2rem,60.5rem); padding-top:2.5rem; } .group { grid-template-columns:2.5rem 1fr; } .person { grid-template-columns:2.4rem minmax(0,1fr); } .actions { grid-column:2; } .letters { display:none; } }
  `

  private onSearch(event: InputEvent) { this.query = (event.target as HTMLInputElement).value; const params = new URLSearchParams(window.location.search); this.query ? params.set('q', this.query) : params.delete('q'); history.replaceState({}, '', `/${params.size ? `?${params}` : ''}`) }
  private setFilter(filter: Filter) { this.filter = filter }
  private get results() { const needle = normalized(this.query); return this.people.filter((person) => { const matchesWords = needle.split(/\s+/).filter(Boolean).every((word) => normalized(person.display_name).includes(word)); const matchesFilter = this.filter === 'all' || (this.filter === 'living' && person.is_living === true) || (this.filter === 'dead' && person.is_living === false); return matchesWords && matchesFilter }) }
  private get groups() { const grouped = new Map<string, PersonSummary[]>(); for (const person of [...this.results].sort((a,b) => a.display_name.localeCompare(b.display_name, 'ru'))) { const key = familyInitial(person); grouped.set(key, [...(grouped.get(key) ?? []), person]) } return [...grouped.entries()] }

  render() {
    const unavailable = this.connectionState === 'unavailable'; const groups = this.groups
    return html`<main aria-live="polite"><span class="eyebrow">Семейный архив</span><h1>Люди семейного архива</h1><p class="lead">Выберите человека, чтобы открыть его страницу или построить дерево от него.</p>
      <section class="catalogue-controls" aria-label="Каталог людей"><input class="catalogue-search" type="search" placeholder="Имя, отчество, фамилия, девичья фамилия или год" .value=${this.query} @input=${this.onSearch} /><div class="filters"><button class="filter ${this.filter === 'all' ? 'active' : ''}" @click=${() => this.setFilter('all')}>Все</button><button class="filter ${this.filter === 'living' ? 'active' : ''}" @click=${() => this.setFilter('living')}>Живущие</button><button class="filter ${this.filter === 'dead' ? 'active' : ''}" @click=${() => this.setFilter('dead')}>Умершие</button><span class="count">${this.results.length} ${this.results.length === 1 ? 'человек' : 'человек'}</span><span class="letters">${groups.map(([letter]) => html`<a href="#letter-${letter}">${letter}</a>`)}</span></div></section>
      ${unavailable ? html`<p class="empty">Не удалось связаться с сайтом. Проверьте подключение и обновите страницу.</p>` : groups.length ? groups.map(([letter, people]) => html`<section class="group" id="letter-${letter}"><div class="letter">${letter}</div><div>${people.map((person) => html`<article class="person"><span class="monogram">${initials(person)}</span><div><a class="name" href="/people/${person.id}">${person.display_name}</a><div class="meta">${person.years ?? 'годы неизвестны'}${person.parents_label ? ` · Родители: ${person.parents_label}` : ''}</div></div><div class="actions"><a class="action" href="/people/${person.id}">Страница</a><a class="action primary" href="/tree?person=${person.id}">Дерево от него</a></div></article>`)}</div></section>`) : html`<p class="empty">${this.people.length ? 'Ничего не найдено.' : 'В семейном архиве пока нет людей.'}</p>`}
    </main>`
  }
}

customElements.define('cats-house-home', CatsHouseHome)
