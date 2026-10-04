import { LitElement, css, html } from 'lit'

type PublicEvent = { event_type: string; date_text: string | null }
type PublicRelation = { id: string; display_name: string }
type PublicMedia = { id: string; original_filename: string; url: string }
type PublicPerson = {
  id: string
  display_name: string
  biography: string | null
  events: PublicEvent[]
  parents: PublicRelation[]
  children: PublicRelation[]
  partners: PublicRelation[]
  media: PublicMedia[]
}

export class CatsPersonCard extends LitElement {
  static properties = { person: { attribute: false } }

  declare person: PublicPerson

  static styles = css`
    :host { display: block; max-width: 42rem; margin: 2rem auto; padding: 1.5rem; }
    h1 { color: var(--cats-ink); font-family: Iowan Old Style, Georgia, serif; font-size: clamp(2rem, 8vw, 4rem); }
    li { margin: 0.5rem 0; color: var(--cats-muted); }
    a { color: var(--cats-accent); }
  `

  render() {
    return html`
      <article>
        <h1>${this.person.display_name}</h1>
        <p><a href="/tree?person=${this.person.id}">Открыть дерево</a></p>
        ${this.person.biography ? html`<p>${this.person.biography}</p>` : ''}
        <h2>События</h2>
        <ul>${this.person.events.map((event) => html`<li>${event.event_type} ${event.date_text ?? ''}</li>`)}</ul>
        ${this.renderRelations('Родители', this.person.parents)}
        ${this.renderRelations('Партнёры', this.person.partners)}
        ${this.renderRelations('Дети', this.person.children)}
        ${this.person.media.length ? html`
          <section>
            <h2>Материалы</h2>
            <ul>${this.person.media.map((item) => html`<li><a href="${item.url}" target="_blank" rel="noopener">${item.original_filename}</a></li>`)}</ul>
          </section>
        ` : ''}
      </article>
    `
  }

  private renderRelations(title: string, relations: PublicRelation[]) {
    if (!relations.length) return ''
    return html`
      <section>
        <h2>${title}</h2>
        <ul>${relations.map((person) => html`<li><a href="/people/${person.id}">${person.display_name}</a></li>`)}</ul>
      </section>
    `
  }
}

customElements.define('cats-person-card', CatsPersonCard)
