/**
 * site/src/theme.ts
 * ====================
 * Alternância de tema claro/escuro, compartilhada entre TODAS as
 * páginas do site (index.html, loja.html, ...) -- script clássico
 * (sem `export`/`import`, ver tsconfig.json: "module": "none"), então
 * cada página só precisa carregar `dist/theme.js` ANTES do seu próprio
 * script pra ganhar a classe `ThemeToggle` como global.
 */

type Theme = "light" | "dark";
const THEME_STORAGE_KEY = "ultron-site-theme";

class ThemeToggle {
  private readonly button: HTMLButtonElement;

  constructor(button: HTMLButtonElement) {
    this.button = button;
    this.button.addEventListener("click", () => this.toggle());
    this.applyStoredOrSystemTheme();
  }

  private toggle(): void {
    const current = document.documentElement.getAttribute("data-theme") as Theme | null;
    const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const next: Theme = (current ?? system) === "dark" ? "light" : "dark";
    this.setTheme(next);
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  }

  private applyStoredOrSystemTheme(): void {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") {
      this.setTheme(stored);
    }
  }

  private setTheme(theme: Theme): void {
    document.documentElement.setAttribute("data-theme", theme);
    this.button.setAttribute("aria-pressed", String(theme === "dark"));
  }
}

function initThemeToggle(): void {
  const themeButton = document.getElementById("theme-toggle");
  if (themeButton instanceof HTMLButtonElement) {
    new ThemeToggle(themeButton);
  }
}

document.addEventListener("DOMContentLoaded", initThemeToggle);
