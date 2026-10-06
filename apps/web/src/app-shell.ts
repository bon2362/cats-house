import { LitElement, css, html } from 'lit'

import { searchOwnerPeople } from './owner-api'
import './pages/person-editor'
import './pages/relative-section'
import { ru } from './locales/ru'
import './pages/home-page'
import type { PersonSummary } from './pages/home-page'
import './pages/person-card'
import './pages/tree-page'
import './pages/login-page'
import { GUEST, fetchOwnerStatus, logoutOwner, type OwnerStatus } from './owner-session'

type ConnectionState = 'loading' | 'ready' | 'unavailable'
type SearchPerson = PersonSummary & { is_archived?: boolean }
type PublicPerson = {
  id: string
  display_name: string
  biography: string | null
  events: { event_type: string; date_text: string | null }[]
  parents: SearchPerson[]
  children: SearchPerson[]
  partners: SearchPerson[]
  media: { id: string; original_filename: string; url: string }[]
}

export class CatsHouseApp extends LitElement {
  static properties = { connectionState: { state: true }, query: { state: true }, people: { state: true }, cataloguePeople: { state: true }, activeResult: { state: true }, person: { state: true }, ownerStatus: { state: true }, ownerError: { state: true }, hiddenPersonId: { state: true } }
  private declare connectionState: ConnectionState
  private declare query: string
  private declare people: SearchPerson[]
  private declare cataloguePeople: PersonSummary[]
  private declare activeResult: number
  private declare person: PublicPerson | null
  private declare ownerStatus: OwnerStatus
  private declare ownerError: string
  private declare hiddenPersonId: string | null
  private searchTimer: number | undefined

  constructor() {
    super()
    this.connectionState = 'loading'; this.query = ''; this.people = []; this.cataloguePeople = []; this.activeResult = -1; this.person = null; this.ownerStatus = GUEST; this.ownerError = ''; this.hiddenPersonId = null
  }

  static styles = css`
    :host { display:block; min-height:100vh; background:var(--paper,var(--cats-paper)); }
    header { display:flex; min-height:4rem; align-items:center; gap:2rem; border-bottom:1px solid var(--border,var(--cats-line)); padding:0 1.875rem; }
    .hidden-person { padding:2rem 1rem; max-width:60rem; margin:0 auto; }
    .brand { flex:none; color:var(--ink,var(--cats-ink)); font-family:var(--font-serif,Georgia,serif); font-size:1.4rem; letter-spacing:-.04em; text-decoration:none; white-space:nowrap; }
    nav { display:flex; align-self:stretch; align-items:center; gap:1.5rem; }
    nav a { color:var(--text-2,var(--cats-muted)); font-size:.875rem; font-weight:600; text-decoration:none; }
    nav a.active { align-self:stretch; border-bottom:2px solid var(--ink,var(--cats-ink)); color:var(--ink,var(--cats-ink)); display:flex; align-items:center; }
    .header-right { display:flex; align-items:center; gap:1.5rem; margin-left:auto; }
    .search { position:relative; width:min(23rem,30vw); }
    input { width:100%; height:2.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; background:var(--sheet,#fff); color:var(--ink,var(--cats-ink)); font:inherit; padding:0 .75rem; }
    input:focus { border-color:var(--green,var(--cats-accent)); box-shadow:0 0 0 3px var(--green-light,#e4ece7); outline:0; }
    .search-menu { position:absolute; z-index:20; top:calc(100% + .5rem); left:0; width:min(42rem,calc(100vw - 3rem)); border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); box-shadow:0 12px 32px rgba(23,24,23,.12); overflow:hidden; }
    .search-result { display:grid; grid-template-columns:2.5rem 1fr; gap:.75rem; width:100%; border:0; background:transparent; color:inherit; cursor:pointer; padding:.75rem 1rem; text-align:left; text-decoration:none; }
    .search-result:hover,.search-result.active { background:var(--green-light,#e4ece7); }
    .monogram { display:grid; width:2.5rem; height:2.5rem; place-items:center; background:var(--subtle,#ececea); color:var(--text-2,#4a4c49); font-size:.75rem; font-weight:700; }
    .result-name { display:block; color:var(--ink,#171817); font-size:.95rem; font-weight:600; line-height:1.3; }
    .result-meta { display:block; color:var(--text-3,#6b6d69); font-size:.8rem; line-height:1.35; }
    .all-results { display:block; border-top:1px solid var(--border,#dcdcd8); color:var(--green,var(--cats-accent)); font-weight:700; padding:.9rem 1rem; text-decoration:none; }
    .owner-link,.owner-state { color:var(--text-2,var(--cats-muted)); font-size:.8125rem; text-decoration:none; white-space:nowrap; }
    .owner-link .short { display:none; }
    .owner-error { color:#7d2b20; font-size:.75rem; max-width:14rem; white-space:normal; }
    .owner-logout { border:0; background:transparent; color:var(--green,var(--cats-accent)); cursor:pointer; font:inherit; font-weight:600; padding:0; }
    @media (max-width:45rem) { header { gap:1rem; padding:0 1rem; } .header-right { gap:.75rem; } .header-right { flex:1 1 auto; min-width:0; justify-content:flex-end; } .search { flex:1 1 auto; min-width:0; width:auto; max-width:11rem; } .owner-link .full { display:none; } .owner-link .short { display:inline; } }
  `

  connectedCallback() { super.connectedCallback(); void this.checkPublicApi(); void this.loadOwnerStatus(); void this.loadCatalogue(); void this.loadPersonFromPath() }
  disconnectedCallback() { super.disconnectedCallback(); if (this.searchTimer) window.clearTimeout(this.searchTimer) }

  private async loadCatalogue() { try { const response = await fetch('/api/v1/people'); const data = response.ok ? await response.json() : []; this.cataloguePeople = Array.isArray(data) ? data : [] } catch { this.cataloguePeople = [] } }
  private async loadPersonFromPath() { const match = window.location.pathname.match(/^\/people\/([^/]+)$/); if (!match) return; const response = await fetch(`/api/v1/people/${match[1]}`); this.person = response.ok ? await response.json() : null; this.hiddenPersonId = response.status === 404 ? match[1] : null }
  private async loadOwnerStatus() { this.ownerStatus = await fetchOwnerStatus() }
  /** The header shows a guest only after the server confirms the session is closed. */
  private async signOut() {
    this.ownerError = ''
    if (await logoutOwner()) {
      this.ownerStatus = { ...this.ownerStatus, authenticated: false }
      this.people = []; this.activeResult = -1
      if (this.searchTimer) window.clearTimeout(this.searchTimer)
    }
    else this.ownerError = 'Не удалось выйти. Проверьте связь и попробуйте ещё раз.'
  }
  private ownerControls() {
    if (this.ownerStatus.authenticated) return html`<span class="owner-state">Владелец · <button class="owner-logout" @click=${this.signOut}>Выйти</button></span>${this.ownerError ? html`<span class="owner-error" role="alert">${this.ownerError}</span>` : ''}`
    const next = `${window.location.pathname}${window.location.search}`
    return html`<a class="owner-link" href="/login?next=${encodeURIComponent(next)}"><span class="full">Вход для владельца</span><span class="short">Владелец</span></a>`
  }
  private async checkPublicApi() { try { const response = await fetch('/api/v1/health'); if (!response.ok) throw new Error('Public API is unavailable'); this.connectionState = 'ready' } catch { this.connectionState = 'unavailable' } }

  private searchPeople(event: InputEvent) { this.query = (event.target as HTMLInputElement).value; this.people = []; this.activeResult = -1; if (this.searchTimer) window.clearTimeout(this.searchTimer); if (!this.query.trim()) return; this.searchTimer = window.setTimeout(() => void this.requestSearch(), 150) }
  private async requestSearch() { if (this.ownerStatus.authenticated) { const session = this.ownerStatus; const result = await searchOwnerPeople(this.query); if (this.ownerStatus !== session) return; this.people = result.ok ? result.value.slice(0, 6) : []; return } try { const response = await fetch(`/api/v1/people?query=${encodeURIComponent(this.query)}`); const data = response.ok ? await response.json() : []; this.people = Array.isArray(data) ? data.slice(0, 6) : [] } catch { this.people = [] } }
  private onSearchKeydown(event: KeyboardEvent) { if (event.key === 'Escape') { this.people = []; this.activeResult = -1; return }; if (!this.people.length) return; if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); const direction = event.key === 'ArrowDown' ? 1 : -1; this.activeResult = (this.activeResult + direction + this.people.length) % this.people.length }; if (event.key === 'Enter' && this.activeResult >= 0) window.location.assign(`/people/${this.people[this.activeResult].id}`) }
  private initials(person: SearchPerson) { return person.display_name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() }

  render() {
    const treeRootId = new URLSearchParams(window.location.search).get('person'); const isTreePage = window.location.pathname === '/tree'; const isLoginPage = window.location.pathname === '/login'
    return html`<header>
      <a class="brand" href="/">${ru.brand}</a><nav aria-label="Основная навигация"><a class=${!isTreePage ? 'active' : ''} href="/">Все люди</a>${isTreePage && treeRootId ? html`<a class="active" href="/tree?person=${treeRootId}">Дерево</a>` : ''}</nav>
      <div class="header-right"><section class="search" aria-label="Поиск по семье"><input type="search" placeholder="Найти человека по имени или фамилии" .value=${this.query} @input=${this.searchPeople} @keydown=${this.onSearchKeydown} />
        ${this.people.length ? html`<div class="search-menu" role="listbox">${this.people.map((person,index) => html`<a class="search-result ${index === this.activeResult ? 'active' : ''}" href="/people/${person.id}" role="option" aria-selected=${index === this.activeResult}><span class="monogram">${this.initials(person)}</span><span><span class="result-name">${person.display_name}</span><span class="result-meta">${person.years ?? 'годы неизвестны'}${person.parents_label ? ` · родители: ${person.parents_label}` : ''}</span>${person.is_archived ? html`<span class="result-meta">скрыт</span>` : ''}</span></a>`)}<a class="all-results" href="/?q=${encodeURIComponent(this.query)}">Все результаты →</a></div>` : ''}
      </section>${this.ownerControls()}</div></header>
      ${isLoginPage ? html`<cats-login-page .status=${this.ownerStatus} .next=${new URLSearchParams(window.location.search).get('next')} @owner-logout-request=${this.signOut}></cats-login-page>` : isTreePage ? html`<cats-tree-page .rootId=${treeRootId} .isOwner=${this.ownerStatus.authenticated}></cats-tree-page>` : !this.person && this.hiddenPersonId && this.ownerStatus.authenticated ? html`<section class="hidden-person"><cats-person-editor .personId=${this.hiddenPersonId} .standalone=${true} @person-visibility-changed=${() => this.loadPersonFromPath()}></cats-person-editor><cats-relative-section .personId=${this.hiddenPersonId} @person-changed=${() => this.loadPersonFromPath()}></cats-relative-section></section>` : this.person ? html`<cats-person-card .person=${this.person} .isOwner=${this.ownerStatus.authenticated} @person-changed=${() => this.loadPersonFromPath()}></cats-person-card>` : html`<cats-house-home .connectionState=${this.connectionState} .people=${this.cataloguePeople}></cats-house-home>`}`
  }
}

customElements.define('cats-house-app', CatsHouseApp)
