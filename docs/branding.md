# Branding assets

The STR Concierge mark — a teal rounded-square house-with-cloche glyph plus the "STR Concierge"
wordmark — lives in one place:

```
custom_components/str_concierge/brand/
```

That folder is canonical. There is no second copy to keep in sync.

## What's in it

| File | Dimensions | Purpose |
|---|---|---|
| `icon.png` | 256 × 256 | Square integration icon |
| `icon@2x.png` | 512 × 512 | hDPI variant of `icon.png` |
| `logo.png` | 695 × 128 | Horizontal logo — glyph + "STR Concierge" wordmark |
| `logo@2x.png` | 1389 × 256 | hDPI variant of `logo.png` |
| `dark_icon.png` | 256 × 256 | Icon optimised for dark backgrounds |
| `dark_icon@2x.png` | 512 × 512 | hDPI variant of `dark_icon.png` |
| `dark_logo.png` | 695 × 128 | Logo optimised for dark backgrounds |
| `dark_logo@2x.png` | 1389 × 256 | hDPI variant of `dark_logo.png` |
| `icon.svg` | vector | Master artwork for the glyph; source for the PNG exports |

All PNGs have transparent backgrounds. `icon.svg` is the design master — HA never reads it, but
every PNG above is exported from it, so edit the SVG first.

## How Home Assistant picks them up

Since **Home Assistant 2026.3**, a custom integration can ship brand images inside its own
package in a `brand/` folder, served through the brands proxy API. Local brand images take
priority over the brands CDN, with no extra configuration. They drive the integration card, the
config flow header, and the device pages.

Submitting to the [`home-assistant/brands`](https://github.com/home-assistant/brands) repo is
**not required** for custom integrations — its `custom_integrations/` folder is a legacy path.

`hacs.json` sets the minimum Home Assistant version to `2026.3.0` to match, so every install
that can add the integration renders the real artwork. If that floor is ever lowered, older
installs will fall back to the generic gear icon — nothing was ever submitted to the brands CDN
for this domain, so there is no CDN fallback to catch them.

## Updating the artwork

1. Edit `icon.svg` and re-export the PNGs at the dimensions in the table above.
2. Drop all nine files into `custom_components/str_concierge/brand/`.
3. Ship it in a normal release — HA picks up the new images once the package is installed.

## Design guidance

Constraints worth preserving if the mark is ever reworked, drawn from the
[brands image specs](https://github.com/home-assistant/brands#adding-a-new-brand):

- **Icons** must be square (1:1). Transparency preferred.
- **Logos** should be landscape, with the shortest side 128–256 px (256–512 px for `@2x`), and an
  aspect ratio that respects the logo itself rather than being padded to a fixed box.
- Trim empty space — images should contain the minimum amount of padding.
- PNG only, lossless, optimised for web.
- The icon has to work small: it should still read at 32 × 32 favicon scale.
- Provide dark variants whenever the light artwork would lose contrast on a dark background.
