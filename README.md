# Double Pump — site components

## Structure
```
index.html              markup
css/styles.css          all styles + design tokens (:root)
js/main.js              header scroll + gallery/lightbox
resources/
  logo.png              YOU ADD — header logo
  hero.png              YOU ADD — hero image
  bathrooms/
    images.json         gallery manifest (file names relative to this folder)
    01.jpg, 01-thumb.jpg, ...   YOU ADD — gallery images
```

## You need to add
- `resources/logo.png` — the header logo (shrinks on scroll via its width).
- `resources/hero.png` — the hero image.
- `resources/bathrooms/*.jpg` — the gallery images referenced by `images.json`.

## Running locally
Galleries use `fetch()`, which browsers block over `file://`. So:
- **Double-click** `index.html` → page renders, galleries show demo placeholders.
- **Serve over http** to load real galleries. From this folder:
  ```
  python3 -m http.server 8000
  ```
  then open http://localhost:8000

## Design tokens
In `:root` at the top of `css/styles.css`:
- `--page-bg`, `--header-bg`
- `--logo-max` / `--logo-min` — logo width expanded vs scrolled
- `--shrink-distance` — scroll px over which the header shrinks
- `--hero-max-h` — hero cap on wide screens
- `--container-max` — width cap before side padding grows
- `--section-pad-x-min` — side padding below the cap
- `--overlap` — how far the first container rises into the hero
- `--container-radius`, `--header-color`, `--underline-color`, `--body-color`
- `--font-serif`, `--font-sans`

## Container component
```html
<section class="section">
  <div class="container">                 <!-- add container--overlap on the first -->
    <div class="container__header"><h1>Title</h1></div>
    <div class="container__content">
      <p>Body copy…</p>                    <!-- add class="is-italic" for italics -->
    </div>
  </div>
</section>
```
Stacked containers auto-space (32px). The underline tracks the header text
width minus 30px.

## Gallery
Point `data-src` at a folder containing `images.json`:
```html
<div class="gallery" data-src="resources/bathrooms"></div>
```
Manifest — file names are relative to the folder; `caption` optional, shows in
the viewer only:
```json
{ "images": [
  { "thumb": "01-thumb.jpg", "full": "01.jpg", "caption": "…" },
  { "thumb": "02-thumb.jpg", "full": "02.jpg" }
]}
```
Absolute paths (`/…`, `http(s):…`, `data:…`) are used as-is. If only one of
thumb/full is given it's used for both. Grid columns add/remove with the
container width; tiles stay 1:1. Viewer pages with on-screen arrows, ← / →
keys, Esc to close, and wraps around.

> The manifest filename looked for inside the folder is `images.json`
> (`MANIFEST` constant in `js/main.js`). Remove the `SAMPLE` fallback block
> before going live.
