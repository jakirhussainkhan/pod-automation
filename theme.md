# Theme (Dark / Light Mode) — Feature Audit

> Scope: the light/dark/system appearance feature across the frontend
> (`app/templates`, `app/static/js`, `app/static/css`).
> Last audited: 2026-10-16 — verified against live code.
> Status: **implemented & working**. This document records *what was built, how it
> works, and where the seams are* for future changes.

---

## 1. TL;DR

- Users can pick **Light**, **Dark**, or **System** (follow OS).
- Preference is stored in the browser (`localStorage`) under the key
  `pod-automation-theme`; it is **not** persisted on the server.
- Dark styling is applied by adding a `dark` class to `<html>`, which drives:
  1. **Tailwind `dark:` utilities** (class-based dark mode), and
  2. **CSS variable tokens** (`:root` vs `html.dark`) + component overrides in `app.css`.
- A tiny inline script in `<head>` applies the theme **before** Tailwind loads to
  avoid a flash of the wrong theme (FOUC).
- Two UI entry points: the **top-bar toggle** (sun/moon icon) and the
  **Settings → Appearance** card (3-way radiogroup, arrow-key navigable).
- OS changes are watched live: when the preference is `system`, switching the
  OS theme updates the page instantly.

---

## 2. How it works (mechanism)

### 2.1 Preference model
- Values: `"light" | "dark" | "system"`.
- Default when nothing is stored (or storage is blocked): `"system"`.
- `"system"` resolves to `"dark"` when `prefers-color-scheme: dark` matches,
  else `"light"`.

### 2.2 Storage key
- `THEME_KEY = "pod-automation-theme"` — defined in `app/static/js/app.js:5`.
- Every read/write is wrapped in `try/catch`: private-mode / disabled storage
  degrades gracefully (in-memory only, falls back to `system` → resolves to
  whatever the OS prefers; if even `matchMedia` is unavailable, light).

### 2.3 Applying the theme
- `document.documentElement.classList.toggle("dark", effective === "dark")`
- `document.documentElement.style.colorScheme = effective` (drives native
  widgets: scrollbars, `date`/`datetime-local` pickers, form controls).
- `<meta name="color-scheme" content="light dark">` (`base.html:6`) tells the
  browser both schemes are supported before any CSS runs.

### 2.4 No-flash early init
`app/templates/base.html:8-26` — an inline `<script>` in `<head>` (before the
Tailwind CDN tag) reads `localStorage`, resolves `light|dark|system`, and adds
the `dark` class + `colorScheme` immediately. This duplicates the *resolution*
logic from `app.js` on purpose: it must run before Tailwind/app.css to prevent a
flash. Keep the two in sync if the rules ever change.

### 2.5 Tailwind class-based dark mode
`app/templates/base.html:27-55`:
```html
<script src="https://cdn.tailwindcss.com/3.4.17"></script>
<script>
  var GREY = { 50:"#fafafa", …, 950:"#0a0a0a" };   // one neutral ramp
  tailwind.config = {
    darkMode: "class",
    theme: { extend: { colors: {
      slate: GREY, gray: GREY, red: GREY, amber: GREY, green: GREY, emerald: GREY
    } } }
  };
</script>
```
CDN version is pinned to `3.4.17`. All `dark:` utilities in templates activate
only when `<html class="dark">` is present. This config is the **single source of
truth for colour**: `slate` (blue-grey by default) *and* the status families
(`red` / `amber` / `green` / `emerald`) are remapped to one neutral ramp so every
utility renders grey — see §8.

### 2.6 CSS token layer
`app/static/css/app.css` defines semantic tokens twice:
- `:root` → light tokens (`app.css:11-24`)
- `html.dark` → dark tokens (`app.css:27-40`)

Tokens: `--bg-main`, `--bg-card`, `--border-card`, `--text-primary`,
`--text-secondary`, `--bg-sidebar`, `--border-subtle`, `--shadow-card`,
`--glass-blur`, `--input-bg`, `--input-border`. Component-level dark overrides
(`html.dark .btn-secondary`, `html.dark .field-input`, `html.dark .toast`,
`html.dark .dash-card`, …) follow the token block. The Dashboard "Obsidian"
surfaces use dedicated `html.dark .dash-*` rules (`app.css:980+`).

### 2.7 Runtime API (`window`)
Exported from `app.js` (`app.js:943-952`):
- `window.PODTheme.get()` → stored preference (`light|dark|system`)
- `window.PODTheme.set(value)` → set + persist + apply
- `window.PODTheme.effective()` → resolved `light|dark`
- `window.setTheme(value)` / `window.getTheme()` → legacy aliases

### 2.8 Change event
`setTheme` and `initTheme`'s OS listener dispatch a DOM `CustomEvent`:
```js
document.dispatchEvent(new CustomEvent("pod-theme-change", {
  detail: { preference, effective }
}));
```
Other modules can listen to react to theme changes (the Appearance card does,
`settings.js:116`).

---

## 3. Entry points

### 3.1 Top-bar toggle
- Markup: `base.html:68-74` — `<button id="theme-toggle">` with two SVGs
  `#theme-icon-sun` (hidden initially) and `#theme-icon-moon`.
- Behaviour (`app.js:99-110`): click resolves the *current effective* theme and
  flips to the opposite of it (so toggling from `system` sets an explicit
  `light`/`dark`).
- `syncThemeIcons()` (`app.js:50-70`) swaps sun/moon and updates
  `aria-label`/`title` ("Switch to light mode" / "Switch to dark mode").

### 3.2 Settings → Appearance card
- Markup: `settings.html:253-262` — a `role="radiogroup"` with three
  `role="radio"` pills (`data-theme-value="light|dark|system"`), plus a hint
  element `#theme-current`.
- Logic (`settings.js:38-123`):
  - `syncThemeOptions(preference, effective)` highlights the active pill
    (`pill-active`), sets `aria-checked`, and roving `tabindex`.
  - Click applies the preference via `window.PODTheme.set` (falls back to
    `window.setTheme`), then toasts.
  - Arrow keys (Left/Right/Up/Down) move selection within the radiogroup
    (`settings.js:99-114`) — WAI-ARIA radiogroup pattern.
  - Listens to `pod-theme-change` to stay in sync with the top-bar toggle.
- Copy: "Choose light or dark mode. Saved in this browser." (`settings.html:255`).

---

## 4. File map (anchors)

| File | What it owns |
|---|---|
| `app/templates/base.html:6` | `color-scheme` meta |
| `app/templates/base.html:8-26` | No-flash early theme init (inline) |
| `app/templates/base.html:27-55` | Tailwind CDN pin + `darkMode: "class"` + monochrome colour remap |
| `app/templates/base.html:34,37,57,…` | `dark:` utilities on body/sidebar/topbar/modals |
| `app/static/css/app.css:1-40` | Token contract (light `:root` / `html.dark`) |
| `app/static/css/app.css:43-60+` | Page background gradients per scheme |
| `app/static/css/app.css:152+` | Component overrides (`html.dark .*`) |
| `app/static/css/app.css:980+` | Dashboard "Obsidian" dark surfaces |
| `app/static/js/app.js:5` | `THEME_KEY` |
| `app/static/js/app.js:11-44` | Read / resolve helpers |
| `app/static/js/app.js:50-70` | Icon + label sync |
| `app/static/js/app.js:76-94` | `setTheme` (apply + persist + emit event) |
| `app/static/js/app.js:99-131` | `initTheme` (toggle wiring + OS listener) |
| `app/static/js/app.js:930-931` | `initTheme()` called on `DOMContentLoaded` |
| `app/static/js/app.js:943-952` | `window.PODTheme` / `setTheme` / `getTheme` exports |
| `app/static/js/settings.js:38-123` | Appearance card controller |
| `app/templates/settings.html:253-262` | Appearance card markup |

---

## 5. What was done (audit of implemented state)

- [x] Three-way preference (`light` / `dark` / `system`) with OS default.
- [x] Persistence via `localStorage` (key `pod-automation-theme`).
- [x] No-FOUC early init in `<head>`.
- [x] Tailwind class-based dark mode (`darkMode: "class"`), CDN pinned.
- [x] CSS variable token layer + per-component dark overrides.
- [x] Top-bar toggle with icon swap and dynamic `aria-label`/`title`.
- [x] Settings Appearance card (radiogroup) with roving focus + arrow keys.
- [x] Live OS-theme listener while preference is `system`.
- [x] `pod-theme-change` custom event for cross-module sync.
- [x] Public API surface (`window.PODTheme`, `window.setTheme`, `window.getTheme`).
- [x] `color-scheme` set on `<html>` so native controls/scrollbars follow.
- [x] Graceful degradation when `localStorage`/`matchMedia` are unavailable.
- [x] Every page inherits the theme (all templates use `dark:` utilities).

---

## 6. Known gaps / notes (candidates for the next change)

1. **Browser-local only.** Preference is not stored on the server, so it does
   not follow the user across browsers/devices. If per-user persistence is
   wanted, add a settings/`preferences` field + hydrate `PODTheme` after load.
2. **Duplicated resolution logic.** The "effective theme" rule exists twice:
   `base.html:12-14` (inline, pre-CSS) and `app.js:39-44`. Any rule change must
   be applied in both places.
3. **Duplicated storage key literal.** `settings.js:70` hardcodes
   `"pod-automation-theme"` as a fallback string instead of reusing
   `PODTheme.get()`; harmless but a drift risk.
4. **Two styling systems coexist.** Tailwind `dark:` utilities and the
   `app.css` token/override layer both target dark mode. New components should
   pick one convention to avoid conflict. Note: `slate`, `red`, `amber`, `green`
   and `emerald` are all remapped to one neutral ramp in the Tailwind config
   (§8), so e.g. `text-red-600` or `dark:text-slate-400` render pure grey.
   Deliberate — keep it in mind when adding markup or a genuinely semantic colour.
5. **Dashboard uses a separate dark token set** (`html.dark .dash-*`), so its
   dark surfaces differ from the Tailwind `dark:bg-slate-900/60` cards used on
   other pages (this is the "two card systems" audit item).
6. **No SRI/fallback on the Tailwind CDN** — if the CDN fails, `dark:`
   utilities (and all Tailwind styling) are lost; only `app.css` survives.
7. **Storage-blocked UX.** In private mode the early script always falls back to
   light on first paint; a subsequent `app.js` run corrects to `system`/dark if
   `matchMedia` is present — a possible one-frame mismatch.
8. **No test coverage.** There are no automated tests for theme
   resolution/`setTheme`/the event contract (JS is untested repo-wide).

---

## 7. How to verify manually

1. Load any page → confirm no flash of the wrong theme on reload.
2. Top-bar icon toggles light ⇄ dark; icon and tooltip update.
3. Settings → Appearance: click Light / Dark / System; active pill + hint text
   update and a toast confirms.
4. Keyboard: Tab into the radiogroup, then Arrow keys move the selection.
5. Set OS to dark/light while preference is **System** → page follows live.
6. DevTools → Application → Local Storage → `pod-automation-theme` reflects the
   last choice; delete it → reverts to System.
7. Check contrast in dark mode for text/badges (AA target).
8. Native controls (date/time inputs, scrollbars) match the active scheme.

---

## 8. Palette neutralization — blue tone removed (2026-10-16)

**Problem:** dark mode had a pervasive **blue cast**. Root cause was the
*palette*, not the architecture:

1. Tailwind's `slate` scale is blue-grey and drove ~170 dark surfaces
   (`dark:bg-slate-900`, `dark:border-slate-700`, `dark:text-slate-400`, …).
2. Custom near-blacks were blue-leaning: `--bg-main #050811`,
   `--bg-sidebar #090d18`, hovers `#161e31`, dash cards `#111726`.
3. Decorative **indigo/sky/violet** radial gradients washed the page background.

**Fix (surfaces neutralized; accent kept):**

| Layer | Change |
|---|---|
| `base.html` Tailwind config | `slate` remapped to the pure-neutral ramp so every `slate-*` utility is grey, in **one place** |
| `base.html` body/sidebar/topbar | `#050811`→`#0a0a0a`, `#090d18`→`#111111` |
| `app.css` tokens (`:root` / `html.dark`) | neutral greys: `--bg-main #0a0a0a`, `--bg-sidebar #111111`, `--bg-card rgba(23,23,23,.72)`, neutral text/borders |
| `app.css` body gradient | indigo/sky/violet glows → faint neutral sheen |
| `app.css` components | all blue-cast hex/rgba (scrollbar, nav hover, icon/btn-secondary, skeleton, toast, field-input, pill, stat-bar, code-block, thumb-fallback, tables, `.dash-*`) → neutral ramp |

**Neutral ramp in use:**
`#fafafa · #f5f5f5 · #e5e5e5 · #d4d4d4 · #a3a3a3 · #737373 · #525252 · #404040 · #262626 · #171717 · #0a0a0a`

### 8.1 Accent → monochrome

All blue/indigo **accents** were replaced with **neutral** ones.

| Element | Before | After |
|---|---|---|
| Primary button / toggle-on / pill-active | `#2563eb` blue | `var(--accent-bg)` = near-black (light) / near-white (dark) |
| Links (`text-blue-600` / `dark:text-blue-400`, `.dash-link`) | blue | `--text-primary` + underline |
| Focus ring (focus-visible, input, toggle) | `#2563eb` / `#818cf8` | `var(--focus-ring)` neutral |
| Nav active | indigo | neutral bg + light/dark text (left rule in both schemes) |
| Info badge `.badge-blue`, `.chip`, `.toast-info` | blue | grey |
| Logs restore bar | indigo | grey |
| Cadence progress fill | `bg-blue-600` | `bg-gray-800 dark:bg-slate-200` |
| Account avatar | `bg-indigo-600` | `bg-gray-800 dark:bg-slate-200` |

New tokens: `--accent-bg`, `--accent-bg-hover`, `--accent-fg`, `--focus-ring`
(light `#18181b` / `#000000` / `#ffffff` / `#18181b`; dark `#fafafa` /
`#d4d4d4` / `#0a0a0a` / `#d4d4d4`).

### 8.2 Status colours → monochrome

For a strictly 100% grey UI the last semantic colours were neutralized too —
**without editing any template or JS file**:

- `base.html` Tailwind config remaps the **cool** families `slate` / `gray` and
  the **status** families `red` / `amber` / `green` / `emerald` to the same
  neutral ramp, so **every** `bg-red-50/80`, `text-red-700`, `dark:text-red-200`,
  `text-gray-500`, `border-amber-200`, `dark:border-emerald-700/60`, … renders
  grey — in **one place**.
- `app.css` component colours recoloured: `.badge-green` / `.badge-amber` /
  `.badge-red`, `.toast-success` / `.toast-error` / `.toast-info`, `.btn-danger`,
  `.field-error`. Severity is now conveyed by **contrast** (`.badge-red` = dark
  chip in light mode / light chip in dark mode = most attention) plus the badge
  text, not by hue.

**Result:** the whole UI is monochrome (neutral ramp only). Verified: **zero**
`blue/indigo/sky/violet/cyan/purple` and **zero** `red/amber/green/emerald` hex
or rgba remain in `app.css`; no `red/amber/green/emerald` hex in templates/JS.
Two files define the entire palette: `base.html` (Tailwind config) + `app.css`.

**Cosmetic leftover:** the class *name* `badge-blue` is kept (used by
`studio.html`, `accounts.js`, `groups.js`, `app.js`) but its rendered colour is
grey. Rename it to `badge-info` only if you want the name to match.

> Note: because `slate` and `gray` are remapped in the Tailwind config (§8),
> reading `dark:text-slate-400` yields pure grey `#a3a3a3` and `text-gray-500`
> yields `#737373`, not Tailwind's default blue-grey. Deliberate; keep it in mind
> when adding markup.
