import { LitElement, css, html } from 'lit'

type PublicEvent = { event_type: string; date_text: string | null }
type PublicPerson = { display_name: string; biography: string | null; events: PublicEvent[] }

export class CatsPersonCard extends LitElement {
  static properties = { person: { attribute: false } }

  declare person: PublicPerson

  static styles = css`
    :host { display: block; max-width: 42rem; margin: 2rem auto; padding: 1.5rem; }
    h1 { color: var(--cats-ink); font-family: Iowan Old Style, Georgia, serif; font-size: clamp(2rem, 8vw, 4rem); }
    li { margin: 0.5rem 0; color: var(--cats-muted); }
  `

  render() {
    return html`
      <article>
        <h1>${this.person.display_name}</h1>
        ${this.person.biography ? html`<p>${this.person.biography}</p>` : ''}
        <h2>События</h2>
        <ul>${this.person.events.map((event) => html`<li>${event.event_type} ${event.date_text ?? ''}</li>`)}</ul>
      </article>
    `
  }
}

customElements.define('cats-person-card', CatsPersonCard)
