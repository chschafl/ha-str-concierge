# Branding assets

This directory holds **placeholder** icon and logo PNGs for STR Concierge. They are intentionally crude (cyan background, "STR" lettering, big "PLACEHOLDER" banner) so they're easy to recognise as not-yet-finished and easy to replace.

## What lives here

| File | Dimensions | Purpose |
|---|---|---|
| `icon.png` | 256 × 256 | The square integration icon |
| `icon@2x.png` | 512 × 512 | 2× resolution variant of `icon.png` (for HiDPI displays) |
| `logo.png` | 256 × 128 | Horizontal logo with wordmark (icon + "STR Concierge" text) |
| `logo@2x.png` | 512 × 256 | 2× resolution variant of `logo.png` |

All four are PNGs with a transparent-friendly opaque background.

## Where these get used

Home Assistant pulls integration brand assets from the central [`home-assistant/brands`](https://github.com/home-assistant/brands) repo at `https://brands.home-assistant.io`. For a custom integration like STR Concierge, the path is:

```
custom_integrations/str_concierge/icon.png
custom_integrations/str_concierge/icon@2x.png
custom_integrations/str_concierge/logo.png
custom_integrations/str_concierge/logo@2x.png
```

Until those files exist in the brands repo:

- The HA UI shows a generic gear icon on the integration card and config flow.
- HACS shows a placeholder thumbnail in the search results.

The files in *this* directory are **the artwork we want to submit** — they don't get loaded by HA at runtime from here, and they don't ship inside the `custom_components/str_concierge/` package.

## How to ship real icons

1. Replace the four files in this directory with proper artwork. Keep the same filenames and dimensions.
2. Open a PR against [`home-assistant/brands`](https://github.com/home-assistant/brands) adding them under `custom_integrations/str_concierge/`. The brands repo has a [contributing guide](https://github.com/home-assistant/brands#contributing) with image specs (transparent background for logos, square aspect for icons, etc.) — follow it.
3. Once merged, HA picks up the new icons on the brands CDN within a few minutes. No release of this repo is required.

## Design guidance

- The placeholder uses `#18BCF2` (HA cyan) as the background, which is fine for the icon but the brands repo prefers **transparent** backgrounds for both icons and logos when possible.
- The icon should "work" small — readable at 32×32 favicon scale.
- The logo should have the wordmark + glyph; keep the brand short ("STR Concierge", maybe with "for Home Assistant" tucked under in a thinner weight if there's room).
- Don't include the word "Placeholder" 🙂

## Regenerating the placeholders (development only)

If you want to tweak the placeholder generation (for example, to change the background colour for a screenshot), the script is below. It only depends on Pillow.

```python
# Run from the repo root after `pip install Pillow`
from PIL import Image, ImageDraw, ImageFont
# … see git history of branding/README.md for the original generator script
```
