# templates/ — CSS & HTML Rules

## CSS variables
Use the app's own variables (defined in `static/style.css`). Never use claude.ai system variables like `var(--color-background-primary)` — the app uses `var(--bg)`, `var(--surface)`, `var(--border)`, `var(--text)`, `var(--muted)`, `var(--accent)`, `var(--danger)`, `var(--success)`.

Theme is switched via `[data-theme="light"]` attribute on `<body>` — not `prefers-color-scheme`.

## Standard control height: 26px
Every interactive element in the topbar and sidebar. Exception: `.toggle` is `32×18px` — do not change to 26px.

## Pill cluster container pattern
```css
display: flex; background: var(--bg); border: 1px solid var(--border);
border-radius: 6px; overflow: hidden;
```
Buttons inside: `border-right: 1px solid var(--border)` as dividers; last child has none. Selected: `background: var(--accent); color: #fff`.

## Danger buttons
Never place destructive actions (delete, reset, disconnect, sign out) inside a pill cluster. Standalone button with `border: 1px solid var(--danger); color: var(--danger)`, separated by a gap. Applies everywhere — topbar, sidebar, modals, list rows.

## Badge sizing standard
All badges — platform, role, source, CPR, faces, Art.9, overdue, risk — use: `font-size: 9px; padding: 1px 5px; border-radius: 10px`. Never override with larger inline styles. New badge classes always start from this standard.

## No emojis in button labels
All buttons use plain text — topbar, filter bar, modals, settings, and lang file values. No `▶ ■ 💾 ⚙ 🕐 ⬇ ⬆ 🗑 📋 ☰ ⊞`.

## Gotchas

- **Label click forwarding** — interactive elements inside `<label>` get clicks forwarded to the label's checkbox. Use `<button type="button">` to prevent this.
