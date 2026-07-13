/**
 * site/src/main.ts
 * ===================
 * BootSequence: digita as linhas do "boot" do núcleo cognitivo no
 * hero, uma letra de cada vez, como um terminal de verdade -- respeita
 * `prefers-reduced-motion` (mostra tudo pronto, sem animação, pra quem
 * pediu menos movimento no sistema).
 *
 * A alternância de tema (ThemeToggle) mora em theme.ts, compartilhada
 * com loja.html -- carregada ANTES deste script (ver index.html).
 */

interface BootLine {
  /** Texto puro da linha (sem HTML) -- ver `renderInto` para o realce. */
  text: string;
  /** Trecho de `text` a destacar na cor de acento (opcional). */
  highlight?: string;
}

/** Nome do operador reconhecido no boot -- mesmo conceito da intro
 * cinematográfica do PC (gui/intro.py: "que bom revê-lo"), só que fixo
 * aqui (o site é estático, não fala com o Ultron de verdade pra saber
 * quem está na tela). Troque pelo seu nome se for reaproveitar este
 * site pra outra instância do Ultron. */
const OPERADOR = "Angelo";

const BOOT_LINES: readonly BootLine[] = [
  { text: "> inicializando núcleo cognitivo...", highlight: "núcleo cognitivo" },
  { text: "> memória local [OK] · plugins [42 carregados]" },
  { text: "> voz [OK] · visão [OK] · automação [OK]" },
  { text: "> nenhuma API externa obrigatória [confirmado]" },
  { text: `> operador reconhecido: que bom revê-lo, ${OPERADOR}`, highlight: OPERADOR },
  { text: "> cognitive core initialized" },
];

const CHARS_PER_TICK = 1;
const TICK_MS = 18;
const LINE_PAUSE_MS = 260;

class BootSequence {
  private readonly container: HTMLElement;
  private readonly reducedMotion: boolean;

  constructor(container: HTMLElement) {
    this.container = container;
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  async run(): Promise<void> {
    if (this.reducedMotion) {
      this.renderInstantly();
      return;
    }
    for (const line of BOOT_LINES) {
      await this.typeLine(line);
      await this.wait(LINE_PAUSE_MS);
    }
    this.container.classList.add("boot-done");
  }

  private renderInstantly(): void {
    for (const line of BOOT_LINES) {
      const el = document.createElement("div");
      el.className = "boot-line";
      el.innerHTML = this.highlightMarkup(line);
      this.container.appendChild(el);
    }
    this.container.classList.add("boot-done");
  }

  private typeLine(line: BootLine): Promise<void> {
    return new Promise((resolve) => {
      const el = document.createElement("div");
      el.className = "boot-line";
      this.container.appendChild(el);

      let shown = 0;
      const tick = (): void => {
        shown = Math.min(line.text.length, shown + CHARS_PER_TICK);
        el.innerHTML = this.highlightMarkup({ text: line.text.slice(0, shown), highlight: line.highlight });
        if (shown < line.text.length) {
          window.setTimeout(tick, TICK_MS);
        } else {
          resolve();
        }
      };
      tick();
    });
  }

  /** Escapa o texto e, se um trecho de destaque já estiver totalmente
   * visível, envolve ele em `<b>` -- feito em cima do texto JÁ
   * escapado, então nunca interpreta o texto do próprio site como
   * marcação (sem risco de injeção, mesmo sendo conteúdo estático
   * nosso). */
  private highlightMarkup(line: BootLine): string {
    const escaped = this.escapeHtml(line.text);
    if (!line.highlight) return escaped;
    const escapedHighlight = this.escapeHtml(line.highlight);
    const idx = escaped.indexOf(escapedHighlight);
    if (idx === -1) return escaped;
    return (
      escaped.slice(0, idx) +
      "<b>" + escapedHighlight + "</b>" +
      escaped.slice(idx + escapedHighlight.length)
    );
  }

  private escapeHtml(raw: string): string {
    const div = document.createElement("div");
    div.textContent = raw;
    return div.innerHTML;
  }

  private wait(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }
}

function main(): void {
  const bootContainer = document.getElementById("boot");
  if (bootContainer) {
    void new BootSequence(bootContainer).run();
  }
}

document.addEventListener("DOMContentLoaded", main);
