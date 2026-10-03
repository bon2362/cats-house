import { LitElement, css, html } from 'lit'

import { ru } from '../locales/ru'

export type ConnectionState = 'loading' | 'ready' | 'unavailable'

export class CatsHouseHome extends LitElement {
  static properties = {
    connectionState: { attribute: false },
  }

  declare connectionState: ConnectionState

  constructor() {
    super()
    this.connectionState = 'loading'
  }

  static styles = css`
    :host {
      display: grid;
      min-height: calc(100vh - 4.5rem);
      place-items: center;
      padding: clamp(2rem, 8vw, 7rem) 1.5rem;
    }

    section {
      width: min(100%, 44rem);
      border-top: 1px solid var(--cats-line);
      padding-top: clamp(1.75rem, 5vw, 3.5rem);
    }

    .eyebrow,
    .status {
      color: var(--cats-accent);
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    h1 {
      max-width: 9ch;
      margin: 0.75rem 0 1.25rem;
      color: var(--cats-ink);
      font-family: Iowan Old Style, Palatino Linotype, Book Antiqua, Georgia, serif;
      font-size: clamp(3rem, 10vw, 6.5rem);
      font-weight: 400;
      letter-spacing: -0.06em;
      line-height: 0.88;
    }

    p {
      max-width: 32rem;
      color: var(--cats-muted);
      font-size: clamp(1rem, 2vw, 1.25rem);
      line-height: 1.55;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 2rem;
      transition: color 180ms ease;
    }

    .dot {
      width: 0.5rem;
      height: 0.5rem;
      border-radius: 50%;
      background: currentColor;
    }

    .unavailable {
      color: #8e382d;
    }
  `

  render() {
    const unavailable = this.connectionState === 'unavailable'

    return html`
      <section aria-live="polite">
        <span class="eyebrow">${ru.familyArchive}</span>
        <h1>${ru.brand}</h1>
        <p>${unavailable ? ru.apiUnavailableHelp : ru.startMessage}</p>
        <span class="status ${unavailable ? 'unavailable' : ''}">
          <span class="dot" aria-hidden="true"></span>
          ${unavailable ? ru.apiUnavailable : ru.preparingTree}
        </span>
      </section>
    `
  }
}

customElements.define('cats-house-home', CatsHouseHome)
