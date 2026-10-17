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

Playwright starts and stops its own temporary server on port 4174. On Linux, Chromium also needs its usual system libraries. To use an existing Chromium installation, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. The Playwright tests cover documentation routes, direct refresh, clipboard prompts, mobile documentation, navigation, all five dashboard screens, invoice details, payment filters, local policy inputs, keyboard control, workflow previews, FAQ, marquee controls, reduced motion, local media, independent image effects, and responsive layouts from 360 to 1440 pixels.

## Interactive dashboard

`src/components/Dashboard.tsx` owns the showcase. Overview is the default; Wallet, Invoices, Payments, and Settings switch through React state without routes or requests. The existing 455 px frame and blue-and-white shell remain. Below 768 px, navigation becomes a horizontal icon row. Longer screens scroll inside the frame, and the Overview fade excludes the desktop sidebar.

Invoice details and payment filters are interactive. Settings inputs are empty examples, stay in memory when switching screens, and can be reset. They never update METRON or Circle. The user-requested 80 USDC is labeled as an illustrative example balance. No live balance, private address, individual historical x402 amount, or additional activity is claimed.

The former evidence spacer now contains the user's editorial photo, extended to 16:9 and matched to the site's blue-and-white palette. It fills the page width between Install and FAQ. CSS applies 1 px blur, 0.9 opacity, 0.85 saturation, and 0.75 brightness, with a white fade only at the top and bottom edges. Responsive checks cover 360, 390, 761, 768, 1024, 1198, and 1440 px.

The hero uses the supplied cloud workspace image as a decorative static background. A local overlay behind the copy supports text contrast, and a 96 px bottom fade joins the white section. The hero defaults to 0.5 px blur, 0.9 opacity, 0.85 saturation, and 0.8 brightness; the editorial photo defaults to 1 px blur, 0.9 opacity, 0.85 saturation, and 0.75 brightness. Eight scoped CSS custom properties in `src/styles.css` configure those effects independently; see [asset treatment](docs/assets.md#image-controls). Crop, scaling, and navigation/dashboard layout are preserved.

## Static Vercel deployment

Import the repository into Vercel and set **Root Directory** to `site`, framework to **Vite**, build command to `npm run build`, and output directory to `dist`. No environment variables, server functions, or runtime credentials are needed. No deployment was performed as part of this implementation.

## Content and design sources

- Installation: repository `docs/INSTALL.md`, root `plugin.json`, and `.agents/plugins/marketplace.json`.
- Product and approval boundaries: repository `README.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, and `docs/PROVIDERS.md`.
- Design: the supplied `design.txt`, with the user's latest USDC blue-and-white palette instruction applied to every section. Primary blue is `#2775CA`, hover blue is `#1D5FA8`, and light blue is `#E5F0FF`.
- Later visual changes: transparent supplied logos with no additional visible labels; no Codex chip; hero, integrations, installation, and FAQ headings use Inter Tight at weight 500 to match How It Works. Installation and FAQ headline sentences have no trailing periods.
- Helper text uses plain English across descriptions, workflow captions, previews, installation steps, and FAQ answers. Financial facts, approval rules, technical status codes, and testnet limits are preserved.
- Navbar and footer branding use the supplied transparent navy logo to the left of METRON. The wordmark matches the hero's Inter Tight medium font and has no trailing period.
- Evidence: this site's original design-brief pass used the supplied historical Arc Testnet facts and incoming transaction URL; no new financial operation or independent private-ledger verification was performed in that pass. The public transaction link does not independently prove invoice or deal status.

The dashboard's bars are explicitly illustrative. The earlier two x402 payments preceded revenue; later, QuickNode intent `SI-000003` settled for 100 atomic USDC after the newer 30 USDC invoice was paid and reconciled. Payment evidence, the posted expense journal, and V3 `X402_SPEND` are confirmed, while original service fulfillment remains MISSING. PR #27 stages responses for future transactions and did not restore the original response. Earned operating capital totals 5.20 USDC as a policy allocation, not a separate wallet transfer. The controlled buyer is not independent commercial traction, and no causal `SUPPORTS` relationship between the QuickNode expense and earlier revenue is proven. The site contains no private messages, buyer/seller email addresses, private ledger, or credentials.

The reference FAQ repeated the integrations specification; this implementation includes one integrations section and one eight-question FAQ. The workflow preview is a scalable HTML/SVG illustration with the reference's fixed frame and transitions. The marketplace manifest and `docs/INSTALL.md` identify four skills. The repository is public at [github.com/riyannode/metronarc](https://github.com/riyannode/metronarc); METRON v0.2.0 is installed and verified with all four skills at baseline `a93781b1d799744cf758961bad1f7d7e6806e6ae`.

See [asset provenance](docs/assets.md) for image sources and treatment.

Latest copy: the hero reads “Give AI Agents Control of Your Business”. The Payments heading reads “Historical x402 payments”, without a numeric prefix. Both generic dollar icons use the supplied transparent USDC mark.
