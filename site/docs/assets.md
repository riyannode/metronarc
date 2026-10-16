# Asset provenance

## Landing page photos

`public/images/metron-cloud-workspace.webp` is the user's supplied `Floating Workspace Above the Clouds.png`, converted at its original 1672 × 941 resolution to WebP (quality 0.86). It is decorative and loads with high priority. CSS applies 0 px blur, full opacity, 0.9 saturation, and 0.85 brightness by default. A local gradient behind the copy supports text contrast, with a separate 96 px fade at the bottom edge. Existing object positioning and 1.04 scaling are preserved.

`public/images/metron-editorial.webp` was created with the built-in imagegen tool from the user's supplied portrait of a seated man surrounded by vintage monitors and research notes. The scene was extended horizontally to 1672 × 941 and given a cool blue-and-white treatment. It occupies the former Anatomy section at a full-width 16:9 ratio, with descriptive alt text and lazy loading. CSS applies 0.5 px blur, full opacity, 0.9 saturation, and 0.85 brightness by default. Only the outer 8% at the top and bottom fades to the neighboring white backgrounds. The asset's existing color grade and edge treatment remain part of the image.

### Image controls

Edit these defaults in `src/styles.css`; no component or dependency change is required:

```css
.hero-backdrop {
  --hero-blur: 0.5px;
  --hero-opacity: 0.9;
  --hero-saturation: 0.85;
  --hero-brightness: 0.8;
}

.editorial-image {
  --editorial-blur: 1px;
  --editorial-opacity: 0.9;
  --editorial-saturation: 0.85;
  --editorial-brightness: 0.75;
}
```

The controls are independent. Opacity runs from `0` to `1`; saturation `1` preserves the source color and `0` removes it. Blur uses a CSS length such as `3px`. Brightness `1` preserves source brightness; `0.85` darkens it by 15%. Neither image asset was replaced during this CSS treatment update. Large or high-DPI displays can still reveal the resolution limit of the existing 1672 × 941 assets.

The previous locally generated gradient video and poster remain in `public/` but are no longer rendered. The photos are served locally; no remote image requests or runtime image-generation calls are used.

Inter and Inter Tight are loaded through Google Fonts under their SIL Open Font License. They are the typefaces named in the reference. Lucide icons use the installed `lucide-react` package under its ISC license. The favicon is a local blue-and-white typographic M.

## Supplied integration logos

The user supplied the Circle, Arc, Gmail, and SQLite images and an x402 website recording. `public/integrations/` contains transparent PNG cutouts of these supplied brand assets. The x402 wordmark was extracted from the top-left of the first video frame. The recording's webpage, metrics, and other content are not embedded in the website. These marks identify tools/components and do not imply partnerships or certification.

Background removal used the built-in imagegen tool, with one request per asset. Prompt set:

- Circle: Extract the exact circular gradient symbol; remove the white background and inner white negative spaces; preserve original gradient, geometry, edges, and proportions; transparent PNG; no redesign, recoloring, shadows, or new text.
- Arc: Extract the exact silver arch; remove the navy/blue background and inner opening; preserve metallic shading and silhouette; transparent PNG; no recoloring, background, shadow, or text.
- Gmail: Extract the exact M logo; remove white background/negative spaces; preserve original red, blue, yellow, and green geometry; transparent PNG; no redesign or new effects.
- SQLite: Extract the complete database, feather, and SQLite wordmark; remove white background/negative spaces; preserve exact lettering and original colors; transparent PNG.
- x402: Extract only the geometric black x402 wordmark in the first frame's top-left; remove all webpage content and background; preserve original proportions; transparent PNG.

Codex is intentionally omitted. The marquee uses logos only, with nonvisual accessible names. Original brand colors are preserved on the blue-and-white site, as requested with the supplied assets. The latest USDC screenshot supplies palette direction only; its coin and decorative objects are not added to the layout.

## METRON brand mark

`public/brand/metron-mark.png` is a transparent cutout of the navy omega-style logo supplied by the user as `ChatGPT Image Sep 28, 2026, 04_28_48 AM.png`. It appears to the left of METRON in the navbar and footer. The text uses Inter Tight at weight 500, matching the hero, with no trailing period. The original navy logo color is retained.

The built-in imagegen tool removed the ivory textured background and all interior negative spaces. Prompt: extract only the original navy omega-style mark; preserve its curves, tapered inner strokes, feet, color, symmetry, and proportions; remove the ivory background and interior negative spaces; tightly crop with a small transparent margin; add no text, glow, shadow, or background.

## USDC mark

`public/brand/usdc.webp` is the user's supplied `Circle_USDC_Logo.svg.webp`, copied unchanged. The 1280 × 1280 source already has transparent corners and 402,051 fully transparent pixels, with antialiased edges. No background removal or regeneration was needed. It replaces every generic dollar icon: the operating wallet header (28 px) and the settlement workflow preview (17 px). Existing icon dimensions and layout are retained.
