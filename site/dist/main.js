"use strict";
/**
 * site/src/main.ts
 * ===================
 * BootSequence: digita as linhas do "boot" do núcleo cognitivo no
 * hero, uma letra de cada vez, como um terminal de verdade -- respeita
 * `prefers-reduced-motion` (mostra tudo pronto, sem animação, pra quem
 * pediu menos movimento no sistema).
 */
/** Nome do operador reconhecido no boot -- mesmo conceito da intro
 * cinematográfica do PC (gui/intro.py: "que bom revê-lo"), só que fixo
 * aqui (o site é estático, não fala com o Ultron de verdade pra saber
 * quem está na tela). Troque pelo seu nome se for reaproveitar este
 * site pra outra instância do Ultron. */
const OPERADOR = "Angelo";
const BOOT_LINES = [
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
    constructor(container) {
        this.container = container;
        this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }
    async run() {
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
    renderInstantly() {
        for (const line of BOOT_LINES) {
            const el = document.createElement("div");
            el.className = "boot-line";
            el.innerHTML = this.highlightMarkup(line);
            this.container.appendChild(el);
        }
        this.container.classList.add("boot-done");
    }
    typeLine(line) {
        return new Promise((resolve) => {
            const el = document.createElement("div");
            el.className = "boot-line";
            this.container.appendChild(el);
            let shown = 0;
            const tick = () => {
                shown = Math.min(line.text.length, shown + CHARS_PER_TICK);
                el.innerHTML = this.highlightMarkup({ text: line.text.slice(0, shown), highlight: line.highlight });
                if (shown < line.text.length) {
                    window.setTimeout(tick, TICK_MS);
                }
                else {
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
    highlightMarkup(line) {
        const escaped = this.escapeHtml(line.text);
        if (!line.highlight)
            return escaped;
        const escapedHighlight = this.escapeHtml(line.highlight);
        const idx = escaped.indexOf(escapedHighlight);
        if (idx === -1)
            return escaped;
        return (escaped.slice(0, idx) +
            "<b>" + escapedHighlight + "</b>" +
            escaped.slice(idx + escapedHighlight.length));
    }
    escapeHtml(raw) {
        const div = document.createElement("div");
        div.textContent = raw;
        return div.innerHTML;
    }
    wait(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
    }
}
function main() {
    const bootContainer = document.getElementById("boot");
    if (bootContainer) {
        void new BootSequence(bootContainer).run();
    }
}
document.addEventListener("DOMContentLoaded", main);
//# sourceMappingURL=main.js.map