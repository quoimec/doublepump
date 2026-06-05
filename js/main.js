/* ============================================================
   HEADER — logo shrinks / menu fades / padding tightens with scroll
   ============================================================ */
(function () {
  const header = document.getElementById('header');
  const DIST = parseFloat(getComputedStyle(document.documentElement)
    .getPropertyValue('--shrink-distance')) || 70;

  function onScroll() {
    // Flip between two states once, at the threshold. CSS transitions the
    // change, so nothing animates layout per scroll frame.
    header.classList.toggle('is-scrolled', window.scrollY > DIST);
  }

  window.addEventListener('scroll', () => requestAnimationFrame(onScroll), { passive: true });
  onScroll();
})();


/* ============================================================
   GALLERIES + PROJECTS (share one photo viewer)

   A gallery folder contains an "images.json" manifest:
     { "images": [ { "thumb": "thumbs/01.jpg", "full": "01.jpg",
                     "caption": "optional" }, ... ] }
   Paths are relative to that folder.

   A .gallery[data-src="folder"] renders a grid of that folder's images.

   A .projects[data-src="base"] renders project cards from
   "base/projects.json":
     { "projects": [
         { "name": "...", "description": "...",
           "folder": "lilyfield",            // gallery dir under base
           "hero":   "lilyfield/hero.jpg" }  // path relative to base
     ] }
   Tapping a card opens the viewer on that project's gallery images.
   ============================================================ */
(function () {
  const MANIFEST = 'images.json';

  // ---- Path helpers ----
  const isAbsolute = p => /^(https?:|data:|\/)/.test(p);
  const join = (folder, p) =>
    (!p || isAbsolute(p)) ? p
      : folder.replace(/\/+$/, '') + '/' + p.replace(/^\/+/, '');

  function normalise(data, folder) {
    const arr = Array.isArray(data) ? data : (data.images || []);
    return arr.map(x => {
      const t = x.thumb || x.full || x.src;
      const f = x.full  || x.thumb || x.src;
      return { thumb: join(folder, t), full: join(folder, f), caption: x.caption };
    });
  }

  async function loadImages(folder) {
    const url = folder.replace(/\/+$/, '') + '/' + MANIFEST;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url} -> ${res.status}`);
    return normalise(await res.json(), folder);
  }

  // ---- Lightbox (shared) ----
  const lb        = document.getElementById('lightbox');
  const lbImg     = document.getElementById('lightbox-img');
  const lbCaption = document.getElementById('lightbox-caption');
  let current = [];
  let idx = 0;

  function show(i) {
    idx = (i + current.length) % current.length;   // wrap around
    const item = current[idx];
    lbImg.src = item.full;
    lbImg.alt = item.caption || '';
    lbCaption.textContent = item.caption || '';
    lbCaption.style.display = item.caption ? '' : 'none';
  }
  function open(list, i) {
    if (!list || !list.length) return;
    current = list;
    lb.classList.add('is-open');
    lb.setAttribute('aria-hidden', 'false');
    show(i || 0);
  }
  function close() {
    lb.classList.remove('is-open');
    lb.setAttribute('aria-hidden', 'true');
    lbImg.src = '';
  }

  lb.querySelector('.lightbox__btn--prev').addEventListener('click', e => { e.stopPropagation(); show(idx - 1); });
  lb.querySelector('.lightbox__btn--next').addEventListener('click', e => { e.stopPropagation(); show(idx + 1); });
  lb.querySelector('.lightbox__btn--close').addEventListener('click', close);
  lb.addEventListener('click', e => { if (e.target === lb) close(); });
  document.addEventListener('keydown', e => {
    if (!lb.classList.contains('is-open')) return;
    if (e.key === 'Escape')     close();
    if (e.key === 'ArrowLeft')  show(idx - 1);
    if (e.key === 'ArrowRight') show(idx + 1);
  });

  /* ---------- Demo placeholders (used when fetch fails, e.g. file://).
     Remove the SAMPLE_* blocks for production. ---------- */
  const rect = (label, shade, w, h) =>
    'data:image/svg+xml;utf8,' + encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">` +
      `<rect width="100%" height="100%" fill="${shade}"/>` +
      `<text x="50%" y="50%" font-family="Arial" font-size="${Math.min(w, h) * 0.18}" ` +
      `fill="#9aa6a8" text-anchor="middle" dominant-baseline="central">${label}</text></svg>`);
  const demoSet = (prefix, shade, n) =>
    Array.from({ length: n }, (_, i) =>
      ({ thumb: rect(`${prefix} ${i + 1}`, shade, 400, 400),
         full:  rect(`${prefix} ${i + 1}`, shade, 1200, 1200) }));

  const SAMPLE_GALLERY = demoSet('Bath', '#d7dedd', 8);

  // ---- Gallery grid ----
  function renderGallery(el, images) {
    el.innerHTML = '';
    images.forEach((img, i) => {
      const fig = document.createElement('figure');
      fig.className = 'gallery__item';
      const im = document.createElement('img');
      im.className = 'gallery__img';
      im.src = img.thumb;
      im.alt = img.caption || '';
      im.loading = 'lazy';
      fig.appendChild(im);
      fig.addEventListener('click', () => open(images, i));
      el.appendChild(fig);
    });
  }

  document.querySelectorAll('.gallery[data-src]').forEach(async el => {
    const folder = (el.dataset.src || '').replace(/\/+$/, '');
    try {
      renderGallery(el, await loadImages(folder));
    } catch (err) {
      console.warn(`Gallery: using demo data (${err}).`);
      renderGallery(el, SAMPLE_GALLERY);
    }
  });

  // ---- Project gallery (full-screen grid overlay) ----
  const pg     = document.getElementById('project-gallery');
  const pgGrid = document.getElementById('project-gallery-grid');

  function openProjectGallery(images) {
    renderGallery(pgGrid, images);   // thumb click -> open() lightbox, reused as-is
    pg.classList.add('is-open');
    pg.setAttribute('aria-hidden', 'false');
  }
  function closeProjectGallery() {
    pg.classList.remove('is-open');
    pg.setAttribute('aria-hidden', 'true');
    pgGrid.innerHTML = '';
  }
  pg.querySelector('.project-gallery__close').addEventListener('click', closeProjectGallery);
  pg.addEventListener('click', e => { if (e.target === pg) closeProjectGallery(); });  // backdrop
  document.addEventListener('keydown', e => {
    // Esc closes the gallery only when the lightbox isn't the thing on top.
    if (e.key === 'Escape' && pg.classList.contains('is-open')
        && !lb.classList.contains('is-open')) closeProjectGallery();
  });

  // ---- Project cards ----
  function renderProjects(el, base, projects) {
    el.innerHTML = '';
    projects.forEach(p => {
      const card = document.createElement('div');
      card.className = 'project';

      const img = document.createElement('img');
      img.className = 'project__img';
      img.src = join(base, p.hero);
      img.alt = p.name || '';
      img.loading = 'lazy';

      const box = document.createElement('div');
      box.className = 'project__card';
      box.innerHTML =
        '<div class="project__text">' +
        '<div class="project__name"></div>' +
        '<div class="project__desc"></div></div>' +
        '<div class="project__plus" aria-hidden="true">+</div>';
      box.querySelector('.project__name').textContent = p.name || '';
      box.querySelector('.project__desc').textContent = p.description || '';

      card.appendChild(img);
      card.appendChild(box);

      card.addEventListener('click', async () => {
        openProjectGallery(await loadImages(join(base, p.folder)));
      });

      el.appendChild(card);
    });
  }

  document.querySelectorAll('.projects').forEach(async el => {
    const base = (el.dataset.src || '').replace(/\/+$/, '');
    const res = await fetch(base + '/projects.json');
    if (!res.ok) throw new Error(`${base}/projects.json -> ${res.status}`);
    const data = await res.json();
    renderProjects(el, base, data.projects || data);
  });
})();

/* ============================================================
   SIDE MENU
   Builds its items from each container's <h1>, gives the owning
   section an id, and links to it via #id. Tapping an item closes
   the menu and smooth-scrolls to that section.
   ============================================================ */
(function () {
  const toggle = document.getElementById('menu-toggle');
  const menu   = document.getElementById('side-menu');
  const list   = document.getElementById('side-menu-list');
  const scrim  = document.getElementById('scrim');
  if (!toggle || !menu || !list || !scrim) return;

  const slug = s => s.toLowerCase().trim()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

  // One menu item per container header; ensure its section has an id.
  document.querySelectorAll('.container__header h1').forEach(h1 => {
    const section = h1.closest('.section') || h1.closest('.container');
    if (!section) return;
    const text = h1.textContent.trim();
    if (!section.id) section.id = slug(text);

    const li = document.createElement('li');
    const a = document.createElement('a');
    a.className = 'side-menu__link';
    a.href = '#' + section.id;
    a.textContent = text;
    li.appendChild(a);
    list.appendChild(li);
  });

  const isOpen = () => menu.classList.contains('is-open');
  function openMenu() {
    menu.classList.add('is-open');
    scrim.classList.add('is-open');
    menu.setAttribute('aria-hidden', 'false');
    toggle.setAttribute('aria-expanded', 'true');
  }
  function closeMenu() {
    menu.classList.remove('is-open');
    scrim.classList.remove('is-open');
    menu.setAttribute('aria-hidden', 'true');
    toggle.setAttribute('aria-expanded', 'false');
  }

  toggle.addEventListener('click', () => isOpen() ? closeMenu() : openMenu());
  scrim.addEventListener('click', closeMenu);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && isOpen()) closeMenu(); });

  const headerEl = document.getElementById('header');

  list.addEventListener('click', e => {
    const a = e.target.closest('.side-menu__link');
    if (!a) return;
    e.preventDefault();
    const id = a.getAttribute('href').slice(1);
    const target = document.getElementById(id);
    closeMenu();
    if (target) {
      history.pushState(null, '', '#' + id);   // reflect position in the URL
      // Scroll manually so the sticky header doesn't cover the section.
      const top = target.getBoundingClientRect().top + window.scrollY
                  - headerEl.offsetHeight - 20;
      window.scrollTo({ top: Math.max(top, 0), behavior: 'smooth' });
    }
  });
})();