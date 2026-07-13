/**
 * site/src/interactions.ts
 * ===========================
 * Camada de interação/animação compartilhada pelas duas páginas
 * (index.html, loja.html) -- script clássico (sem `export`/`import`,
 * ver tsconfig.json: "module": "none"), carregado ANTES de main.ts e
 * loja.ts pra expor essas funções como globais.
 *
 * `initScrollChrome()` roda sozinha (barra de progresso + nav com
 * blur ao rolar não dependem de conteúdo dinâmico). `initScrollReveal()`
 * e `initGlowSurfaces()` são chamadas explicitamente por main.ts (conteúdo
 * já está no HTML) e por loja.ts (DEPOIS de render() criar os cards --
 * se rodassem sozinhas aqui no DOMContentLoaded, executariam ANTES do
 * catálogo existir, e não achariam nenhum ".app-card").
 *
 * Tudo respeita `prefers-reduced-motion`: sem IntersectionObserver
 * disponível ou com o SO pedindo menos movimento, os elementos
 * simplesmente aparecem prontos, sem animação nem brilho de cursor.
 */

function reduceMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Revela `[data-reveal]` (fade + leve subida) quando entra na tela --
 * uma vez só por elemento (para de observar depois de revelar). */
function initScrollReveal(root: ParentNode = document): void {
  const elements = root.querySelectorAll<HTMLElement>("[data-reveal]:not(.is-visible)");
  if (elements.length === 0) return;

  if (reduceMotion() || !("IntersectionObserver" in window)) {
    elements.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.12, rootMargin: "0px 0px -60px 0px" },
  );
  elements.forEach((el) => observer.observe(el));
}

/** Brilho que segue o cursor dentro de cards/linhas (".glow-surface")
 * -- atualiza `--mx`/`--my` (posição relativa ao próprio elemento),
 * lidos por um gradiente radial no CSS. Puramente cosmético: sem
 * cursor/toque, o elemento continua com o hover simples de sempre. */
function initGlowSurfaces(root: ParentNode = document): void {
  if (reduceMotion()) return;
  const surfaces = root.querySelectorAll<HTMLElement>(".glow-surface:not([data-glow-bound])");
  surfaces.forEach((el) => {
    el.dataset.glowBound = "1";
    el.addEventListener("pointermove", (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${event.clientX - rect.left}px`);
      el.style.setProperty("--my", `${event.clientY - rect.top}px`);
    });
  });
}

/** Barra de progresso de leitura no topo + nav ganha fundo/blur depois
 * de rolar um pouco -- os dois só dependem da posição de scroll, nunca
 * de conteúdo que ainda pode não existir, então rodam direto. */
function initScrollChrome(): void {
  const nav = document.querySelector<HTMLElement>(".site-nav");
  const progress = document.querySelector<HTMLElement>(".scroll-progress");
  if (!nav && !progress) return;

  let ticking = false;
  const update = (): void => {
    ticking = false;
    const scrollTop = window.scrollY;
    if (nav) nav.classList.toggle("scrolled", scrollTop > 40);
    if (progress) {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const pct = max > 0 ? Math.min(100, (scrollTop / max) * 100) : 0;
      progress.style.width = `${pct}%`;
    }
  };
  const onScroll = (): void => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(update);
  };

  update();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
}

document.addEventListener("DOMContentLoaded", initScrollChrome);
