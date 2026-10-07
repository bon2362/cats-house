import { LitElement, css, html, nothing } from 'lit'

import { deleteMedia, fetchOwnerMedia, setPortrait, updateMedia, uploadMedia, type ApiResult, type MediaItem, type OwnerMediaItem } from '../owner-api'

type Upload = { name: string; status: string }

/** «Фото и документы»: a gallery for everyone; upload, captions, portrait, hide and delete for the owner. */
export class CatsMediaSection extends LitElement {
  static properties = { personId: { attribute: false }, media: { attribute: false }, isOwner: { attribute: false }, items: { state: true }, uploads: { state: true }, editing: { state: true }, caption: { state: true }, dateLabel: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  /** The guest list from the person page; the owner list is loaded separately and includes hidden files. */
  declare media: MediaItem[]
  declare isOwner: boolean
  private declare items: OwnerMediaItem[] | null
  private declare uploads: Upload[]
  private declare editing: string | null
  private declare caption: string
  private declare dateLabel: string
  private declare error: string
  private declare busy: boolean
  confirm: (text: string) => boolean = (message) => window.confirm(message)

  constructor() { super(); this.personId = ''; this.media = []; this.isOwner = false; this.items = null; this.uploads = []; this.editing = null; this.caption = ''; this.dateLabel = ''; this.error = ''; this.busy = false }

  static styles = css`
    :host { display:block; }
    .tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:16px; }
    @media (max-width:480px) { .tiles { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    .tile { display:grid; gap:6px; align-content:start; min-width:0; }
    .tile.hidden { opacity:.55; }
    .tile a { display:block; color:inherit; text-decoration:none; }
    .tile img { width:100%; aspect-ratio:1; object-fit:cover; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:#f3f3f1; display:block; }
    .doc { aspect-ratio:1; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:#f7f7f5; display:grid; place-items:center; align-content:center; gap:8px; padding:8px; text-align:center; font-size:.8rem; overflow-wrap:anywhere; }
    .doc-icon { font:700 1rem Inter,system-ui,sans-serif; color:#7d2b20; border:2px solid currentColor; border-radius:3px; padding:6px 8px; }
    .caption { margin:0; font-size:.85rem; font-weight:600; overflow-wrap:anywhere; }
    .date { margin:0; font-size:.8rem; color:var(--text-3,#6b6d69); }
    .badge { justify-self:start; font-size:.7rem; font-weight:700; padding:2px 6px; border-radius:3px; background:var(--green,#24513f); color:#fff; }
    .badge.muted { background:#6b6d69; }
    .controls { display:flex; flex-wrap:wrap; gap:4px; }
    button { min-height:1.9rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .55rem; background:#fff; color:var(--green,var(--cats-accent)); font:600 .75rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    .toolbar { display:flex; gap:12px; align-items:center; margin-bottom:16px; }
    .toolbar input[type="file"] { display:none; }
    .uploads { list-style:none; padding:0; margin:0 0 16px; display:grid; gap:4px; font-size:.85rem; }
    form { display:grid; gap:6px; }
    form input { height:2rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .4rem; font:inherit; min-width:0; }
    .empty { margin:0; color:var(--text-3,var(--cats-muted)); line-height:1.5; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() { super.connectedCallback(); if (this.isOwner) void this.load() }

  willUpdate(changed: Map<string, unknown>) {
    const switched = (key: string) => changed.has(key) && changed.get(key) !== undefined
    if ((switched('isOwner') || switched('personId')) && this.isOwner && this.isConnected) void this.load()
  }

  private async load() {
    const result = await fetchOwnerMedia(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.items = result.value
  }

  private changed() { this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true })) }

  /** Run an owner action, then reload the list and tell the page; a refusal is shown in place. */
  private async act(request: Promise<ApiResult<unknown>>) {
    if (this.busy) return
    this.busy = true; this.error = ''
    const result = await request
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.editing = null
    await this.load()
    this.changed()
  }

  private async upload(event: Event) {
    const input = event.target as HTMLInputElement
    const files = [...(input.files ?? [])]
    if (!files.length) return
    this.uploads = files.map((file) => ({ name: file.name, status: 'загружается…' }))
    let uploaded = 0
    for (const [index, file] of files.entries()) {
      // One by one: a refused file shows its own reason and does not stop the others.
      const result = await uploadMedia(this.personId, file)
      if (result.ok) uploaded += 1
      this.uploads = this.uploads.map((item, position) => (position === index ? { ...item, status: result.ok ? 'готово' : result.message } : item))
    }
    input.value = ''
    if (uploaded) { await this.load(); this.changed() }
  }

  private edit(item: OwnerMediaItem) { this.editing = item.id; this.caption = item.caption ?? ''; this.dateLabel = item.date_label ?? '' }

  private removeFile(item: OwnerMediaItem) {
    if (!this.confirm(`Удалить файл «${item.original_filename}»? Он исчезнет с сайта.`)) return
    void this.act(deleteMedia(item.id))
  }

  private picture(item: MediaItem) {
    return html`<a href=${item.file_url} target="_blank" rel="noopener">${item.preview_url
      ? html`<img src=${item.preview_url} alt=${item.caption || item.original_filename} loading="lazy" />`
      : html`<span class="doc"><span class="doc-icon">PDF</span>${item.original_filename}</span>`}</a>`
  }

  private captionForm(item: OwnerMediaItem) {
    const save = (event: Event) => { event.preventDefault(); void this.act(updateMedia(item.id, { caption: this.caption, date_label: this.dateLabel })) }
    return html`<form @submit=${save}>
      <input name="caption" aria-label="Подпись" placeholder="Подпись" maxlength="500" .value=${this.caption} @input=${(event: Event) => { this.caption = (event.target as HTMLInputElement).value }} />
      <input name="date_label" aria-label="Дата" placeholder="Дата, например «около 1950»" maxlength="64" .value=${this.dateLabel} @input=${(event: Event) => { this.dateLabel = (event.target as HTMLInputElement).value }} />
      <div class="controls"><button class="primary" type="submit">Сохранить</button><button type="button" @click=${() => { this.editing = null }}>Отмена</button></div>
    </form>`
  }

  private ownerTile(item: OwnerMediaItem) {
    const photo = Boolean(item.preview_url)
    return html`<div class="tile ${item.is_published ? '' : 'hidden'}" data-media-id=${item.id}>
      ${this.picture(item)}
      ${item.is_portrait ? html`<span class="badge">Портрет</span>` : nothing}
      ${item.is_published ? nothing : html`<span class="badge muted">скрыт</span>`}
      ${this.editing === item.id ? this.captionForm(item) : html`${item.caption ? html`<p class="caption">${item.caption}</p>` : nothing}${item.date_label ? html`<p class="date">${item.date_label}</p>` : nothing}`}
      <div class="controls">
        ${this.editing === item.id ? nothing : html`<button @click=${() => this.edit(item)}>Изменить подпись</button>`}
        ${item.is_portrait
          ? html`<button @click=${() => this.act(setPortrait(this.personId, null))}>Убрать портрет</button>`
          : photo && item.is_published ? html`<button @click=${() => this.act(setPortrait(this.personId, item.id))}>Сделать портретом</button>` : nothing}
        <button @click=${() => this.act(updateMedia(item.id, { is_published: !item.is_published }))}>${item.is_published ? 'Скрыть' : 'Показать'}</button>
        <button @click=${() => this.removeFile(item)}>Удалить</button>
      </div>
    </div>`
  }

  private guestTile(item: MediaItem) {
    return html`<div class="tile" data-media-id=${item.id}>
      ${this.picture(item)}
      ${item.caption ? html`<p class="caption">${item.caption}</p>` : nothing}
      ${item.date_label ? html`<p class="date">${item.date_label}</p>` : nothing}
    </div>`
  }

  render() {
    if (!this.isOwner) {
      return this.media.length ? html`<div class="tiles">${this.media.map((item) => this.guestTile(item))}</div>` : html`<p class="empty">Фото и документы пока не добавлены</p>`
    }
    const items = this.items ?? []
    return html`<div class="toolbar">
        <button class="primary" @click=${() => this.shadowRoot?.querySelector<HTMLInputElement>('input[type="file"]')?.click()}>Загрузить файлы</button>
        <span class="empty">JPEG, PNG или PDF, до 10 МБ</span>
        <input type="file" multiple accept="image/jpeg,image/png,application/pdf" @change=${this.upload} />
      </div>
      ${this.uploads.length ? html`<ul class="uploads">${this.uploads.map((item) => html`<li>${item.name}: ${item.status}</li>`)}</ul>` : nothing}
      ${this.error ? html`<p role="alert">${this.error}</p>` : nothing}
      ${items.length ? html`<div class="tiles">${items.map((item) => this.ownerTile(item))}</div>` : html`<p class="empty">Фото и документы пока не добавлены</p>`}`
  }
}

customElements.define('cats-media-section', CatsMediaSection)
