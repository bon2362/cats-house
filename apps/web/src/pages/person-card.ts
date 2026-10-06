import { LitElement, css, html, nothing } from 'lit'
import './person-editor'
import './family-editor'
import './relative-section'

type PublicEvent = {
  event_type: string
  date_text: string | null
  date_label_ru?: string | null
  place?: string | null
  description?: string | null
}
type PublicRelation = { id: string; display_name: string }
type PublicMedia = { id: string; original_filename: string; url: string }
type PublicPerson = {
  id: string; display_name: string; biography: string | null; events: PublicEvent[]; parents: PublicRelation[]; children: PublicRelation[]; partners: PublicRelation[]; siblings?: PublicRelation[]; media: PublicMedia[]
  birth_label_ru?: string | null; death_label_ru?: string | null
  birth_year?: number | null; death_year?: number | null
  birth_place?: string | null; death_place?: string | null; is_living?: boolean | null
  birth_surname?: string | null; sex?: string | null
}

const eventNames: Record<string, string> = { BIRT: 'Рождение', BIRTH: 'Рождение', DEAT: 'Смерть', DEATH: 'Смерть', MARR: 'Брак', DIV: 'Развод', BURI: 'Погребение', RESI: 'Место жительства', OCCU: 'Занятие', MILI: 'Военная служба', EDUC: 'Образование', BAPM: 'Крещение', CHR: 'Крещение' }
const russianMonths: Record<string, string> = { JAN: 'января', FEB: 'февраля', MAR: 'марта', APR: 'апреля', MAY: 'мая', JUN: 'июня', JUL: 'июля', AUG: 'августа', SEP: 'сентября', OCT: 'октября', NOV: 'ноября', DEC: 'декабря' }

function formatDate(value: string | null): string {
  if (!value) return 'дата неизвестна'
  const cleaned = value.trim()
  const dated = cleaned.match(/^(ABT|CAL|EST|BEF|AFT)?\s*(\d{1,2})?\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{4})$/i)
  if (dated) {
    const [, qualifier, day, month, year] = dated
    const prefix = qualifier ? ({ ABT: 'ок. ', CAL: 'ок. ', EST: 'ок. ', BEF: 'до ', AFT: 'после ' }[qualifier.toUpperCase()] ?? '') : ''
    return `${prefix}${day ? `${day} ` : ''}${russianMonths[month.toUpperCase()]} ${year}`
  }
  const simple = cleaned.match(/^(ABT|CAL|EST|BEF|AFT)\s+(\d{4})$/i)
  if (simple) return `${({ ABT: 'ок. ', CAL: 'ок. ', EST: 'ок. ', BEF: 'до ', AFT: 'после ' }[simple[1].toUpperCase()] ?? '')}${simple[2]}`
  return cleaned
}

function eventDate(event: PublicEvent): string { return event.date_label_ru?.trim() || formatDate(event.date_text) }
function eventYear(event: PublicEvent): string { return (event.date_label_ru ?? event.date_text ?? '').match(/\d{4}/)?.[0] ?? '—' }
function initials(name: string): string { return (name.match(/[A-Za-zА-Яа-яЁё]+/g) ?? []).slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '—' }

export class CatsPersonCard extends LitElement {
  static properties = { person: { attribute: false }, isOwner: { attribute: false }, editing: { state: true }, saved: { state: true }, familyRevision: { state: true } }
  declare person: PublicPerson
  declare isOwner: boolean
  private declare editing: boolean
  private declare saved: boolean
  /** Shared by «Связи» and «Добавить родственника»: a change in one makes the other reload or close. */
  private declare familyRevision: number

  constructor() { super(); this.isOwner = false; this.editing = false; this.saved = false; this.familyRevision = 0 }

  private bumpFamily = () => { this.familyRevision += 1 }

  willUpdate(changed: Map<string, unknown>) {
    if (changed.has('isOwner') && !this.isOwner) this.editing = false
    if (changed.has('isOwner') && this.isOwner && new URLSearchParams(window.location.search).get('edit') === '1') this.editing = true
  }

  private onSaved() {
    this.editing = false
    this.saved = true
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }

  static styles = css`
    :host { display:block; color:var(--ink, var(--cats-ink)); background:var(--paper, var(--cats-paper)); } * { box-sizing:border-box; }
    a { color:var(--green, var(--cats-accent)); text-decoration:none; } a:hover { color:var(--green-dark, var(--cats-accent)); text-decoration:underline; }
    .page { max-width:1200px; margin:0 auto; padding:54px 28px 100px; display:grid; grid-template-columns:200px minmax(0,1fr); gap:64px; }
    .contents { position:sticky; top:32px; align-self:start; border-left:1px solid var(--border, var(--cats-line)); padding-left:16px; display:grid; gap:12px; font-size:14px; }.contents a { color:var(--text-2,var(--cats-muted)); }.contents a:first-child { color:var(--green,var(--cats-accent)); margin-bottom:8px; }
    main { min-width:0; }.eyebrow,.section-kicker { color:var(--green,var(--cats-accent)); font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; margin:0 0 10px; }.hero { display:grid; grid-template-columns:200px minmax(0,1fr); gap:30px; align-items:start; padding-bottom:56px; border-bottom:1px solid var(--border,var(--cats-line)); }.monogram { width:200px; height:250px; background:var(--green-light,#e4ece7); display:grid; place-items:center; color:var(--green,var(--cats-accent)); font-size:48px; font-weight:600; border-radius:3px; }
    h1,h2,h3 { font-family:var(--font-serif,Georgia,serif); color:var(--ink,var(--cats-ink)); } h1 { font-size:clamp(38px,5vw,52px); line-height:1; letter-spacing:-.035em; margin:0 0 16px; font-weight:500; } h2 { font-size:32px; line-height:1.1; margin:0 0 24px; font-weight:500; } h3 { font-family:var(--font-ui,inherit); font-size:15px; margin:0 0 12px; }.life { font-size:18px; color:var(--text-2,var(--cats-muted)); margin:0 0 22px; }.bio { max-width:620px; color:var(--text-2,var(--cats-muted)); line-height:1.6; margin:0 0 24px; }.actions { display:flex; flex-wrap:wrap; gap:10px; }.button { display:inline-flex; align-items:center; min-height:40px; padding:0 16px; border:1px solid var(--green,var(--cats-accent)); border-radius:3px; font:600 14px var(--font-ui,inherit); }.button.primary { background:var(--green,var(--cats-accent)); color:#fff; }
    button.button { background:transparent; color:var(--green,var(--cats-accent)); cursor:pointer; } .saved { align-self:center; color:var(--green,var(--cats-accent)); }
    section { scroll-margin-top:24px; padding:52px 0; border-bottom:1px solid var(--border,var(--cats-line)); }.family-map { min-height:128px; background:var(--band,#efefec); border:1px solid var(--border,var(--cats-line)); padding:20px; display:flex; align-items:center; gap:16px; overflow:auto; margin-bottom:28px; }.mini-card { background:var(--sheet,#fff); border:1px solid var(--card-border,var(--cats-line)); padding:13px 14px; min-width:150px; border-radius:3px; font-size:14px; }.mini-card.focus { background:var(--green,var(--cats-accent)); border-color:var(--green,var(--cats-accent)); color:#fff; }.connector { width:30px; height:1px; flex:0 0 30px; background:var(--line,var(--cats-line)); }.family-columns { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:28px; }.relation-list { margin:0; padding:0; list-style:none; display:grid; gap:8px; }.relation-list a { font-weight:600; }.empty { margin:0; color:var(--text-3,var(--cats-muted)); line-height:1.5; }.union { padding:0 0 14px; margin-bottom:14px; border-bottom:1px solid var(--border,var(--cats-line)); }.union:last-child { border-bottom:0; }.children { padding-left:15px; margin:10px 0 0; display:grid; gap:6px; }
    .timeline { display:grid; gap:0; }.event { display:grid; grid-template-columns:86px minmax(0,1fr); gap:18px; padding:16px 0; border-top:1px solid var(--border,var(--cats-line)); }.event-year { font-family:var(--font-serif,Georgia,serif); font-size:24px; line-height:1; }.event-name { font-weight:600; margin-bottom:3px; }.event-date { color:var(--text-2,var(--cats-muted)); }.media { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:12px; }.media a { border:1px solid var(--card-border,var(--cats-line)); min-height:100px; padding:14px; display:flex; align-items:end; overflow-wrap:anywhere; background:var(--sheet,#fff); }
    @media (max-width:760px) { .page { display:block; padding:28px 18px 72px; }.contents { display:flex; position:static; overflow:auto; border-left:0; border-bottom:1px solid var(--border,var(--cats-line)); padding:0 0 14px; margin-bottom:30px; white-space:nowrap; }.contents a:first-child { margin:0 10px 0 0; }.hero { grid-template-columns:1fr; gap:22px; }.monogram { width:100%; height:160px; }.family-columns { grid-template-columns:1fr; gap:24px; } section { padding:38px 0; } }
  `

  render() {
    const person = this.person
    const events = [...(person.events ?? [])].filter((event) => this.hasVisibleDetail(event)).sort((a, b) => this.eventSortKey(a).localeCompare(this.eventSortKey(b)))
    const life = this.lifeLine(person, events)
    return html`<div class="page"><nav class="contents" aria-label="Разделы страницы человека"><a href="/">← Все люди</a><a href="#family">Семья</a><a href="#timeline">Хронология</a><a href="#biography">Биография</a><a href="#media">Фото и документы</a></nav><main>${this.editing ? html`<cats-person-editor .personId=${person.id} @person-saved=${this.onSaved} @editor-cancel=${() => { this.editing = false }} @person-visibility-changed=${this.onSaved}></cats-person-editor>` : html`<header class="hero"><div class="monogram" aria-label="Монограмма">${initials(person.display_name)}</div><div><p class="eyebrow">Профиль человека</p><h1>${person.display_name}</h1>${person.birth_surname ? html`<p class="life">${person.sex === 'F' ? 'урождённая' : person.sex === 'M' ? 'урождённый' : 'при рождении'} ${person.birth_surname}</p>` : nothing}${life ? html`<p class="life">${life}</p>` : html`<p class="life">Годы жизни в архиве не указаны</p>`}${person.biography ? html`<p class="bio">${person.biography}</p>` : nothing}<div class="actions">${this.isOwner ? html`<button class="button" @click=${() => { this.editing = true; this.saved = false }}>Изменить</button>` : nothing}${this.saved ? html`<span class="saved" role="status">Сохранено</span>` : nothing}<a class="button primary" href="/tree?person=${person.id}">Построить дерево</a><a class="button" href="${window.location.href}">Скопировать ссылку</a></div></div></header>`}<section id="family"><p class="section-kicker">Связи в архиве</p><h2>Семья</h2>${this.renderFamilyMap()}<div class="family-columns"><div><h3>Родители</h3>${this.renderRelationList(person.parents,'Родители в архиве не указаны')}</div><div><h3>Союзы и дети</h3>${this.renderUnions()}</div><div><h3>Братья и сёстры</h3>${this.renderRelationList(person.siblings ?? [], 'Братья и сёстры в архиве пока не указаны')}</div></div>${this.isOwner ? html`<cats-family-editor .personId=${person.id} .revision=${this.familyRevision} @person-changed=${this.bumpFamily}></cats-family-editor><cats-relative-section .personId=${person.id} .revision=${this.familyRevision} @person-changed=${this.bumpFamily}></cats-relative-section>` : nothing}</section><section id="timeline"><p class="section-kicker">По датам</p><h2>Хронология</h2>${events.length ? html`<div class="timeline">${events.map((event) => this.renderEvent(event))}</div>` : html`<p class="empty">Хронология пока не заполнена</p>`}</section><section id="biography"><p class="section-kicker">Личная история</p><h2>Биография</h2>${person.biography ? html`<p class="bio">${person.biography}</p>` : html`<p class="empty">Биография пока не написана</p>`}</section><section id="media"><p class="section-kicker">Архив</p><h2>Фото и документы</h2>${(person.media ?? []).length ? html`<div class="media">${person.media.map((item) => html`<a href="${item.url}" target="_blank" rel="noopener">${item.original_filename}</a>`)}</div>` : html`<p class="empty">Фото и документы пока не добавлены</p>`}</section></main></div>`
  }

  private lifeLine(person: PublicPerson, events: PublicEvent[]) {
    const birthEvent = events.find((event) => ['BIRT', 'BIRTH'].includes(event.event_type))
    const deathEvent = events.find((event) => ['DEAT', 'DEATH'].includes(event.event_type))
    const birth = person.birth_label_ru?.trim() || (person.birth_year ? String(person.birth_year) : birthEvent ? eventDate(birthEvent) : '')
    const death = person.death_label_ru?.trim() || (person.death_year ? String(person.death_year) : deathEvent ? eventDate(deathEvent) : '')
    if (!birth && !death) return ''
    const born = birth ? `${birth}${person.birth_place ? `, ${person.birth_place}` : ''}` : '?'
    const died = death ? `${death}${person.death_place ? `, ${person.death_place}` : ''}` : person.is_living ? 'н. в.' : '?'
    return `${born} — ${died}`
  }
  private renderFamilyMap() { const people = [this.person.parents?.[0], this.person, this.person.partners?.[0], this.person.children?.[0]].filter(Boolean) as (PublicRelation | PublicPerson)[]; return html`<div class="family-map" aria-label="Ближайшая семья">${people.map((person,index) => html`${index ? html`<span class="connector"></span>` : nothing}<div class="mini-card ${person.id === this.person.id ? 'focus' : ''}">${person.display_name}</div>`)}</div>` }
  private renderRelationList(relations: PublicRelation[], empty: string) { return relations?.length ? html`<ul class="relation-list">${relations.map((person) => html`<li><a href="/people/${person.id}">${person.display_name}</a></li>`)}</ul>` : html`<p class="empty">${empty}</p>` }
  private renderUnions() { const partners = this.person.partners ?? []; const children = this.person.children ?? []; if (!partners.length && !children.length) return html`<p class="empty">Союзы и дети в архиве не указаны</p>`; return html`${partners.map((partner) => html`<div class="union"><a href="/people/${partner.id}">${partner.display_name}</a><div class="children">${children.length ? children.map((child) => html`<a href="/people/${child.id}">Ребёнок · ${child.display_name}</a>`) : html`<span class="empty">Дети в архиве не указаны</span>`}</div></div>`)}${!partners.length ? this.renderRelationList(children,'') : nothing}` }
  private hasVisibleDetail(event: PublicEvent) { return ['DEAT', 'DEATH'].includes(event.event_type) || Boolean(event.date_label_ru?.trim() || event.date_text?.trim() || event.place?.trim() || event.description?.trim()) }
  private eventSortKey(event: PublicEvent) { return event.date_label_ru ?? event.date_text ?? '' }
  private renderEvent(event: PublicEvent) {
    const facts = [eventDate(event), event.place?.trim()].filter((value) => value && value !== 'дата неизвестна')
    if (!facts.length && ['DEAT', 'DEATH'].includes(event.event_type)) facts.push('Дата смерти неизвестна.')
    return html`<article class="event"><div class="event-year">${eventYear(event)}</div><div><div class="event-name">${eventNames[event.event_type] ?? 'Событие'}</div>${facts.length ? html`<div class="event-date">${facts.join(' · ')}</div>` : nothing}${event.description?.trim() ? html`<div class="event-date">${event.description.trim()}</div>` : nothing}</div></article>`
  }
}

customElements.define('cats-person-card', CatsPersonCard)
