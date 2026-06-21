# @metis/web

The team-facing Metis SPA — the context-exoskeleton product surface (UX/UI epics B–H). React +
Vite + TypeScript. This replaces the single-file debug console at the gateway's `/` once it reaches
feature parity (~M2); until then it runs alongside it via the Vite dev server.

## Develop

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173, proxying the API to the gateway
```

The dev server proxies the gateway's top-level API prefixes (`/users`, `/workspaces`, `/actions`, …)
to `http://localhost:8000` by default. Point it elsewhere with `VITE_GATEWAY_URL`:

```bash
VITE_GATEWAY_URL=http://localhost:8001 npm run dev
```

Run the gateway separately (from the repo root) so the proxied calls resolve.

## Checks

```bash
npm run check        # typecheck (tsc) + lint (eslint) + production build
```

`npm run check` is the frontend gate, mirroring the Python side's `make check`. CI runs it as a
separate `web` job.

## Layout

- `src/styles/tokens.css` — design tokens (calm palette, scope/sensitivity/routing/risk colors,
  light + dark). The single source of truth for color and spacing.
- `src/styles/global.css` — base reset, accessible focus, reduced-motion.
- `src/domain/types.ts` — shared domain unions (scope, sensitivity, routing, risk) + labels.
- `src/components/` — the shared, accessible primitives: `Badge` (+ domain badges), `Button`,
  `Card`, `Drawer`, and the `EmptyState`/`ErrorState`/`BlockedState` panels.
- `src/App.tsx` — the B1 design-system gallery (a living style guide; replaced by the app shell in
  B2).
