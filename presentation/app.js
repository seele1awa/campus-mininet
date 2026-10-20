const slides = Array.from(document.querySelectorAll(".slide"));
const progressBar = document.getElementById("progressBar");
const pageNumber = document.getElementById("pageNumber");
const prevButton = document.getElementById("prevSlide");
const nextButton = document.getElementById("nextSlide");
const deck = document.getElementById("deck");

let current = 0;

function preloadImages() {
  const images = Array.from(document.images);
  return Promise.all(
    images.map((image) => {
      image.loading = "eager";
      if (image.complete && image.naturalWidth > 0) {
        return Promise.resolve();
      }
      return new Promise((resolve) => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", resolve, { once: true });
      });
    })
  );
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setScale() {
  const marginX = 28;
  const marginY = 86;
  const scale = Math.min(
    (window.innerWidth - marginX) / 1600,
    (window.innerHeight - marginY) / 900
  );
  deck.style.setProperty("--deck-scale", String(Math.max(0.1, scale)));
}

function render() {
  slides.forEach((slide, index) => {
    slide.classList.toggle("active", index === current);
    slide.setAttribute("aria-hidden", index === current ? "false" : "true");
  });

  const total = slides.length;
  const progress = ((current + 1) / total) * 100;
  progressBar.style.width = `${progress}%`;
  pageNumber.textContent = `${current + 1} / ${total}`;
  document.title = `${current + 1}/${total} 基于 Mininet 的校园网构建汇报`;
}

function goTo(index) {
  current = clamp(index, 0, slides.length - 1);
  render();
}

function next() {
  goTo(current + 1);
}

function prev() {
  goTo(current - 1);
}

prevButton.addEventListener("click", prev);
nextButton.addEventListener("click", next);

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
    event.preventDefault();
    next();
  }

  if (event.key === "ArrowLeft" || event.key === "PageUp") {
    event.preventDefault();
    prev();
  }

  if (event.key === "Home") {
    event.preventDefault();
    goTo(0);
  }

  if (event.key === "End") {
    event.preventDefault();
    goTo(slides.length - 1);
  }
});

window.addEventListener("resize", setScale);
window.addEventListener("load", () => {
  setScale();
  render();
  preloadImages().then(() => {
    document.body.classList.add("images-ready");
  });
});

window.addEventListener("beforeprint", () => {
  setScale();
  document.body.classList.add("print-mode");
});

window.addEventListener("afterprint", () => {
  document.body.classList.remove("print-mode");
});

setScale();
render();
