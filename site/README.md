# METRON landing page

React, TypeScript, Tailwind CSS, and Framer Motion. The site is a public product showcase with no connection to the METRON runtime, wallet, Gmail, or SQLite.

## Local development

Requires Node.js 22 and npm.

```sh
cd site
npm ci
npm run dev -- --port 4173
```

Open `http://127.0.0.1:4173`. All local servers bind to loopback.

## Validation

```sh
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm test
```

Playwright starts and stops its own temporary server on port 4174. On Linux, Chromium also needs its usual system libraries. To use an existing Chromium installation, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. The 23 tests cover navigation, all five dashboard screens, invoice details, payment filters, local policy inputs, keyboard control, workflow previews, FAQ, marquee controls, reduced motion, local media, and responsive layouts from 360 to 1440 pixels.

## Interactive dashboard

`src/components/Dashboard.tsx` owns the showcase. Overview is the default; Wallet, Invoices, Payments, and Settings switch through React state without routes or requests. The existing 455 px frame and blue-and-white shell remain. Below 768 px, navigation becomes a horizontal icon row. Longer screens scroll inside the frame, and the Overview fade excludes the desktop sidebar.

Invoice details and payment filters are interactive. Settings inputs are empty examples, stay in memory when switching screens, and can be reset. They never update METRON or Circle. The user-requested 80 USDC is labeled as an illustrative example balance. No live balance, private address, individual historical x402 amount, or additional activity is claimed.

The former evidence spacer now contains the user's editorial photo, extended to 16:9 and matched to the site's blue-and-white palette. It fills the page width between Install and FAQ. CSS blur, reduced saturation, and soft edge fades keep it subdued. Responsive checks cover 360, 390, 761, 768, 1024, 1198, and 1440 px.

The hero uses the supplied cloud workspace image as a decorative static background. Blur and blue-and-white overlays preserve text contrast; the image fades to white toward the dashboard. Neither photo changes the existing navigation or dashboard layout.

## Static Vercel deployment

Import the repository into Vercel and set **Root Directory** to `site`, framework to **Vite**, build command to `npm run build`, and output directory to `dist`. No environment variables, server functions, or runtime credentials are needed. No deployment was performed as part of this implementation.

## Content and design sources

- Installation: repository `docs/INSTALL.md`, root `plugin.json`, and `.agents/plugins/marketplace.json`.
- Product and approval boundaries: repository `README.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, and `docs/PROVIDERS.md`.
- Design: the supplied `design.txt`, with the user's latest USDC blue-and-white palette instruction applied to every section. Primary blue is `#2775CA`, hover blue is `#1D5FA8`, and light blue is `#E5F0FF`.
- Later visual changes: transparent supplied logos with no additional visible labels; no Codex chip; hero, integrations, installation, and FAQ headings use Inter Tight at weight 500 to match How It Works. Installation and FAQ headline sentences have no trailing periods.
- Helper text uses plain English across descriptions, workflow captions, previews, installation steps, and FAQ answers. Financial facts, approval rules, technical status codes, and testnet limits are preserved.
- Navbar and footer branding use the supplied transparent navy logo to the left of METRON. The wordmark matches the hero's Inter Tight medium font and has no trailing period.
- Evidence: the historical Arc Testnet facts and incoming transaction URL supplied in the brief. No financial operation or independent private-ledger verification was performed. The public transaction link does not independently prove invoice or deal status.

The dashboard's bars are explicitly illustrative. Earned operating capital is an allocation, not an executed post-revenue x402 purchase. The two historical x402 payments preceded revenue. The site contains no private messages, buyer/seller email addresses, private ledger, or credentials.

The reference FAQ repeated the integrations specification; this implementation includes one integrations section and one eight-question FAQ. The workflow preview is a scalable HTML/SVG illustration with the reference's fixed frame and transitions. The marketplace manifest and `docs/INSTALL.md` identify four skills. The repository is private, so installation currently requires existing GitHub access.

See [asset provenance](docs/assets.md) for image sources and treatment.

Latest copy: the hero reads “Give AI Agents Power to Run Business”. The Payments heading reads “Historical x402 payments”, without a numeric prefix. Both generic dollar icons use the supplied transparent USDC mark.
