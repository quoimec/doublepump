(function () {
  const grid = document.getElementById("portfolio-grid");
  const lightbox = document.getElementById("lightbox");
  const lbImg = document.getElementById("lightbox-img");
  const btnClose = document.getElementById("lightbox-close");
  const btnPrev = document.getElementById("lightbox-prev");
  const btnNext = document.getElementById("lightbox-next");

  let images = [];
  let current = 0;

  fetch("portfolio/portfolio.json")
    .then((r) => r.json())
    .then((files) => {
      images = files;
      files.forEach((file, i) => {
        const img = document.createElement("img");
        img.src = "portfolio/" + file;
        img.alt = "Portfolio image";
        img.className = "portfolio-thumb";
        img.addEventListener("click", () => open(i));
        grid.appendChild(img);
      });
    })
    // .catch(() => {
    //   grid.textContent = "No portfolio images found.";
    // });

  function open(i) {
    current = i;
    lbImg.src = "portfolio/" + images[current];
    lightbox.classList.add("active");
  }

  function close() {
    lightbox.classList.remove("active");
  }

  function prev() {
    current = (current - 1 + images.length) % images.length;
    lbImg.src = "portfolio/" + images[current];
  }

  function next() {
    current = (current + 1) % images.length;
    lbImg.src = "portfolio/" + images[current];
  }

  btnClose.addEventListener("click", close);
  btnPrev.addEventListener("click", prev);
  btnNext.addEventListener("click", next);

  lightbox.addEventListener("click", (e) => {
    if (e.target === lightbox) close();
  });

  document.addEventListener("keydown", (e) => {
    if (!lightbox.classList.contains("active")) return;
    if (e.key === "Escape") close();
    if (e.key === "ArrowLeft") prev();
    if (e.key === "ArrowRight") next();
  });
})();