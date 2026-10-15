# Asset provenance

`public/hero-blue.mp4` and `public/hero-poster.jpg` were generated locally for this site. No third-party video, screenshot, avatar, or remote product image is embedded. The brief did not establish redistribution permission for the original CDN video, so it was replaced with a soft blue-and-white gradient video to follow the user's latest USDC palette reference. The reference's video placement, looping playback, opacity, depth overlays, and hero composition are retained.

Recreate these assets with FFmpeg:

```sh
ffmpeg -f lavfi -i 'gradients=size=1280x960:rate=24:c0=0xf5f9ff:c1=0x92baff:c2=0xffffff:c3=0xe0ecff:x0=0:y0=0:x1=1280:y1=960:nb_colors=4:speed=0.015:type=radial' -t 12 -c:v libx264 -preset fast -crf 26 -pix_fmt yuv420p -movflags +faststart -an public/hero-blue.mp4
ffmpeg -i public/hero-blue.mp4 -frames:v 1 public/hero-poster.jpg
```

The video is decorative. A still poster remains available when autoplay is unavailable, and playback is paused for reduced-motion users.

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
