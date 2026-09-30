# Quant research dashboard (frontend)

A Svelte 5 + SvelteKit single-page app for exploring captured market data and screening
strategy research. It is a static build (`adapter-static`, `ssr = false`) that talks to the
FastAPI service in `tradingview_data/api.py`.

**No dummy data.** Nothing in this app ships with, generates or simulates market data. Every
number on screen comes from (a) the backend (`/api/*`) or (b) a file the user imports in the
tab. With an empty backend the UI shows empty states only. This is enforced by component tests
(`src/routes/pages.svelte.spec.ts`) and by strict validation of every payload
(`src/lib/api/validate.ts`).

## Run it

```bash
# backend (from the repo root)
pip install -e ".[api]"
tvdata serve --data-dir data                 # http://127.0.0.1:8000

# development: Vite proxies /api to :8000, so no CORS setup is needed
cd frontend && pnpm install && pnpm dev

# production: build once, let FastAPI host it
pnpm build
tvdata serve --data-dir data --static-dir frontend/build
```

Checks: `pnpm check` (svelte-check), `pnpm lint` (prettier + eslint), `pnpm test`
(unit + browser component tests). Component tests run in headless Chromium:
`pnpm exec playwright install chromium` once per machine.

## Design system

[`DESIGN.md`](DESIGN.md) is the source of truth for every visual decision (it is the attached
Framer-style spec, normalised so its front matter parses). `src/routes/layout.css` implements it,
and `src/lib/design/tokens.spec.ts` fails if any color, spacing, radius or type token in the
front matter drifts from the CSS, or if a text/background pairing the UI uses drops below WCAG
contrast (4.5:1 text, 3:1 graphics).

- **Dark only.** Canvas `#090909`, surfaces `#141414` / `#1c1c1c`, hairlines `#262626` / `#1a1a1a`.
  Depth comes from surface lift, not shadows. There is no light mode and no theme toggle.
- **Type.** Inter Variable for text, using the official Latin subset from `inter-ui` so the
  `cv01 cv05 cv09 cv11 ss03 ss07 dlig` character variants work (Google's build strips them).
  Geist stands in for GT Walsheim in display type, as the spec suggests. Tracking is stored in
  `em`, so the negative percentages hold as sizes step down at 1199px and 809px.
- **Shapes.** Every CTA is a pill (`rounded-pill`); the only bordered controls are form fields.
  Primary = white pill, secondary = charcoal pill (`secondary` on the canvas, `translucent` inside
  cards, where surface-1 would vanish). Press feedback is `scale(0.96)`.
- **Accent.** `#0099ff` appears only as hyperlink, focus and selection colour: focus ring, the
  highlight of chart bars that match a filter, `link` buttons.
- **Gradient spotlight cards** (`SpotlightCard`) are scarce: at most one per page, only for the
  empty state or the dataset summary. Text on each stop keeps at least 4.5:1.
- **Responsive.** Tablet breakpoint 810px: the nav collapses into a hamburger overlay (loaded on
  first use), dataset rows stack instead of scrolling sideways.

Adaptations for a dense analytical tool, where the marketing spec is silent or insufficient:

| Spec                                       | Here                                                                                       | Why                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| No second chromatic accent                 | Up = `semantic-success`, down = `gradient-coral`, series = gradient family + white + muted | Market direction needs two colors; both are documented tokens   |
| Focus ring `rgba(0,153,255,.15) 0 0 0 1px` | Same halo plus a solid 1px `#0099ff` edge                                                  | A 15% 1px ring alone is not reliably visible to keyboard users  |
| ~1199px content width                      | Full-width container up to 1600px                                                          | Charts and 10+ column tables need the room                      |
| Buttons 10px 15px padding (34px tall)      | Same on desktop, 44px minimum on touch pointers                                            | Spec says 44px tap targets but its padding gives 34px           |
| Marketing display sizes                    | `display-xl` only on the Datasets hero; tool pages use `display-md`                        | A 62-110px heading costs too much vertical space in a workbench |

UI primitives are [shadcn-svelte](https://shadcn-svelte.com) (bits-ui), restyled onto the tokens in
`src/lib/components/ui`. 21st.dev components are React/TSX and cannot be installed into a Svelte
project, so this is the Svelte port of the same design system.

## Layout

```
src/lib/
  api/         contracts.ts (wire types) · validate.ts (runtime checks) · client.ts (fetch, retry, abort)
  indicators/  127 indicators, 158 outputs; pure functions over typed arrays (see its spec files)
  filters/     types · operators · engine (vectorised masks) · tree · edit · catalog
  explorer/    field keys · BarSource (memoised indicator compute) · generated presets · catalog
  research/    column model for the results table · catalog
  analysis/    event-study.ts (conditional forward returns)
  charts/      canvas controllers (candles, lines) + pure viewport / decimation / scale maths
  data/        csv.ts (client-side OHLCV import, same rules as the backend loader)
  design/      tokens.spec.ts (DESIGN.md <-> CSS parity and contrast checks)
  state/       runes-based stores, provided through context (see below)
  components/  app/ (charts, virtual list, spotlight, empty/error states, menu) · filters/ · explorer/ · research/ · ui/
src/routes/    /  (datasets) · /explorer/[[dataset]] · /research
```

## Backend contract

| Endpoint                      | Client method  | Store                       | Screen                    |
| ----------------------------- | -------------- | --------------------------- | ------------------------- |
| `GET /api/datasets`           | `listDatasets` | `DatasetsStore.load`        | Datasets, dataset pickers |
| `GET /api/datasets/{id}/bars` | `getBars`      | `ExplorerStore.openBackend` | Explorer                  |
| `POST /api/research/run`      | `runResearch`  | `ResearchStore.run`         | Research                  |

`GET /api/health` and `GET /api/datasets/{id}/report` exist on the server but are not used yet.
Errors arrive as `{"detail": string}` or FastAPI's validation list; both become an `ApiError`
(`kind`: `network | timeout | aborted | http | contract`, `retryable`). GETs retry twice on
network faults / 5xx; the research POST never retries. Responses that break the contract
(mismatched column lengths, unsorted time axis, unknown schema version) are rejected, not
rendered. Timestamps are UTC epoch seconds end to end.

## State contracts

State lives in classes with `$state` fields, created once by `AppState` and shared with
`createContext` (`getApp()`), per the Svelte guidance to prefer this over module singletons and
`svelte/store`. Large payloads use `$state.raw`. Components never mutate stores directly:
filter trees are edited through a `FilterEditor` (`patch / add / remove / replace / reset`).

- **`DatasetsStore`**: `items` (backend, starts `[]`), `status`, `error`, `local` (imported in
  this tab, memory only), `usable`, `isEmpty`, `load()`, `importFile(file)`, `removeLocal(id)`.
  A superseded `load()` is aborted and its result ignored.
- **`ExplorerStore`** (created by the explorer route so the indicator library stays out of the
  initial bundle): `bars`, `indicators`, `filter`, `horizons`, `onsetOnly`, `showVolume`; derived
  `source → evaluation → eventMask → matches / study`, `chart`, `referencedFields`;
  `openBackend(id)`, `openLocal(bars)`, `addIndicator / updateIndicator / removeIndicator /
toggleIndicator`, `filterEditor`, `focusBar(i)`.
- **`ResearchStore`**: form (`selectedIds`, `feeBps`, `periodsPerYear`) with `validation` and
  `canRun`; `report` (null until a run succeeds), `table`, `filter`, `evaluation`, sorted `order`;
  `run()`, `cancel()`, `setSort`, `toggleColumn`, `toggleCompare` (max 6), `open(id)`.
- **`SavedFilters(scope)`**: user-named filters in `localStorage`, re-validated on load,
  degrading to memory-only if storage fails.

## Filter engine

`ColumnSource` = typed columns + `ordered` flag. A filter is a tree of groups (ALL/ANY, NOT) and
conditions; each condition compiles to a `Uint8Array` mask, cached per leaf (LRU). Rules:

- Missing values (`NaN`, indicator warm-up) never satisfy a condition.
- Incomplete conditions are skipped; unknown fields or bad operands are **reported** as issues
  and match nothing. They are never silently ignored.
- 22 operators: comparison (also against another field), ranges, crosses, N-bar streaks and
  breakouts, top/bottom percent, validity, text. Crossing/streak operators need ordered data.
- Top/bottom percent rank against the whole sample (look-ahead), so the UI flags them as
  descriptive only.

The explorer exposes every indicator output (158 at default parameters, tunable) as a filter
field, and generates 1,282 presets from the registry; the research table exposes 53+ columns.

## Component reference (main props)

| Component                   | Props                                                                                                                             |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `VirtualList`               | `count`, `itemHeight`, `label`, `key?`, `minWidth?`, `class?` (must bound the height), snippets `header?`, `row(index)`, `empty?` |
| `CandleChart`               | `columns`, `overlays`, `panes`, `mask`, `showVolume`, `label`, `focus?`, `intraday?`                                              |
| `LineChart`                 | `series`, `label`                                                                                                                 |
| `FilterBuilder`             | `tree`, `editor`, `catalog`, `evaluation`, `saved`, `unit`                                                                        |
| `FieldPicker`               | `catalog`, `value`, `onchange`, `numericOnly?`, `placeholder?`                                                                    |
| `ParamEditor`               | `specs`, `values`, `onchange(values)`, `title?`                                                                                   |
| `ResultsTable`              | `research`, `table`                                                                                                               |
| `EventStudyPanel`           | `study`, `horizons`, `onhorizons`, `onsetOnly`, `ononset`                                                                         |
| `EmptyState` / `ErrorPanel` | `title`, `description?`, `icon?` / `error`, `title?`, `onretry?`                                                                  |

## Performance

- Virtual scrolling (`VirtualList`) for datasets, matching bars and results: a 5,000-row result
  set renders < 60 DOM rows (tested), a 100,000-row list < 40.
- Canvas charts draw only the visible window, bucket bars per pixel column when zoomed out,
  and coalesce redraws into one animation frame.
- Indicators are computed once per (indicator, parameters) and shared by chart and filters.
  Measured at 500,000 bars in Node (`src/lib/explorer/performance.spec.ts`): cold compound filter
  (RSI + SMA + volume breakout) ~120 ms, editing a threshold ~6 ms, unchanged re-evaluation ~2 ms.
  That is fast enough that compute stays on the main thread; the pure functions are worker-ready
  if larger captures demand it.
- Route-level code splitting: first load is ~88 kB gzip (JS + CSS) for the datasets page, ~149 kB for
  research and ~167 kB for the explorer (which carries the indicator library). The mobile menu and
  its dialog primitive load on first open. Fonts are self-hosted: Inter subset 97 kB, Geist latin
  28 kB, both `font-display: swap`, fetched only for the glyphs on screen.

## Svelte audit (against the official `svelte-core-bestpractices` guidance)

Runes mode is forced project-wide. No `$:`, `export let`, `on:`, `<slot>`, `use:`, `class:` or
`svelte/store` in app code. `$effect` is used four times, all to sync with something outside
Svelte (three push props into canvas controllers inside `{@attach}`, one maps the URL to the
store). All 35 `{#each}` blocks are keyed. Derived values use `$derived`; `$state.raw` holds
API payloads and typed arrays. `svelte-check` and `eslint-plugin-svelte` (including
`prefer-svelte-reactivity` and `no-navigation-without-resolve`) pass with no findings.

## Known limits

- Imported CSVs are explorer-only and live in memory; the backend has no upload endpoint.
- Timestamps without a timezone in an imported CSV are read as UTC (the backend assumes
  Asia/Kolkata for such files, which only shifts axis labels).
- The forward-return study ignores costs and slippage; percentile filters look ahead.
- `/api/datasets/{id}/report` (technical summary) is not surfaced in the UI yet.
