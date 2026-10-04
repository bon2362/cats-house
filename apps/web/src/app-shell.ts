import { LitElement, css, html } from 'lit'

import { ru } from './locales/ru'
import './pages/home-page'

type ConnectionState = 'loading' | 'ready' | 'unavailable'

export class CatsHouseApp extends LitElement {
  static properties = {
    connectionState: { state: true },
  }

  private declare connectionState: ConnectionState

  constructor() {
    super()
    this.connectionState = 'loading'
  }

  static styles = css`
    :host {
      display: block;
      min-height: 100vh;
      background: var(--cats-paper);
    }

    header {
      display: flex;
      min-height: 4.5rem;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--cats-line);
      padding: 0 1.5rem;
    }

    .brand {
      color: var(--cats-ink);
      font-family: Iowan Old Style, Palatino Linotype, Book Antiqua, Georgia, serif;
      font-size: 1.4rem;
      letter-spacing: -0.04em;
      text-decoration: none;
    }

    nav {
      display: flex;
      align-items: center;
      gap: clamp(0.9rem, 3vw, 2rem);
    }

    a {
      color: var(--cats-ink);
      font-size: 0.875rem;
      text-decoration: none;
    }

    nav a {
      position: relative;
    }

    nav a::after {
      position: absolute;
      right: 0;
      bottom: -0.45rem;
      left: 0;
      height: 1px;
      background: var(--cats-accent);
      content: '';
      transform: scaleX(0);
      transform-origin: right;
      transition: transform 180ms ease;
    }

    nav a:hover::after,
    nav a:focus-visible::after {
      transform: scaleX(1);
      transform-origin: left;
    }

    .sign-in {
      border: 1px solid var(--cats-accent);
      border-radius: 999px;
      color: var(--cats-accent);
      padding: 0.45rem 0.8rem;
      transition: background 180ms ease, color 180ms ease;
    }

    .sign-in:hover,
    .sign-in:focus-visible {
      background: var(--cats-accent);
      color: var(--cats-paper);
    }

    @media (max-width: 32rem) {
      header {
        padding: 0 1rem;
      }

      .brand {
        font-size: 1.15rem;
      }

      nav {
        gap: 0.75rem;
      }
    }
  `

  connectedCallback() {
    super.connectedCallback()
    void this.checkPublicApi()
  }

  private async checkPublicApi() {
    try {
      const response = await fetch('/api/v1/health')
      if (!response.ok) {
        throw new Error('Public API is unavailable')
      }
      this.connectionState = 'ready'
    } catch {
      this.connectionState = 'unavailable'
    }
  }

  render() {
    return html`
      <header>
        <a class="brand" href="/">${ru.brand}</a>
        <nav aria-label="Основная навигация">
          <a href="/tree">${ru.tree}</a>
          <a href="/search">${ru.search}</a>
          <a class="sign-in" href="/login">${ru.signIn}</a>
        </nav>
      </header>
      <cats-house-home .connectionState=${this.connectionState}></cats-house-home>
    `
  }
}

customElements.define('cats-house-app', CatsHouseApp)
