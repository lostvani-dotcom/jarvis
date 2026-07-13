/**
 * site/src/loja.ts
 * ===================
 * Catálogo da loja -- cada app criado vira um item nesta lista e a
 * página se desenha sozinha a partir dela (ver `render()`). Adicionar
 * um novo app no futuro é só adicionar um objeto em `CATALOGO`, nada
 * de mexer no HTML.
 */

interface AppEntry {
  id: string;
  nome: string;
  categoria: string;
  resumo: string;
  descricao: string;
  versaoNome: string;
  versaoCodigo: number;
  tamanhoMb: number;
  requisito: string;
  arquivo: string;
  /** Letra/glifo mostrado no "ícone" desenhado em CSS (ver .app-icon). */
  glifo: string;
  atualizadoEm: string;
}

const CATALOGO: readonly AppEntry[] = [
  {
    id: "ultron-companion",
    nome: "Ultron Companion",
    categoria: "Produtividade",
    resumo: "O Ultron no seu bolso -- controla o celular e conversa com o núcleo do PC pela Wi-Fi.",
    descricao:
      "Chat com o Ultron direto do celular, encaminha notificações (Instagram/WhatsApp/Telegram/Signal/" +
      "Discord) e responde comandos do aparelho (bateria, lanterna, volume, alarme, localização e mais) " +
      "mesmo com o app fechado. Boa parte das funções roda 100% offline no próprio celular -- conversa " +
      "aberta e memória completa pedem o Ultron do PC na mesma rede (ou, se já sincronizado uma vez, " +
      "conversa direto com a nuvem sem precisar do PC ligado).",
    versaoNome: "1.5",
    versaoCodigo: 6,
    tamanhoMb: 5.4,
    requisito: "Android 8.0 ou superior",
    arquivo: "apps/ultron-companion.apk",
    glifo: "U",
    atualizadoEm: "13/07/2026",
  },
  {
    id: "ultron-loja",
    nome: "Loja Ultron",
    categoria: "Sistema",
    resumo: "A própria loja -- descobre o Ultron na rede e instala/atualiza os apps do ecossistema com um toque.",
    descricao:
      "App dedicado só a isso: procurar o Ultron na Wi-Fi de casa, listar o catálogo publicado por ele " +
      "(GET /loja/catalogo) e baixar/instalar qualquer app da lista -- sem loja de terceiros, sem conta, " +
      "sem rastreamento. O mesmo catálogo que alimenta esta página também alimenta o app.",
    versaoNome: "1.0",
    versaoCodigo: 1,
    tamanhoMb: 5.3,
    requisito: "Android 8.0 ou superior",
    arquivo: "apps/ultron-loja.apk",
    glifo: "L",
    atualizadoEm: "13/07/2026",
  },
  {
    id: "redcore-mobile",
    nome: "RedCore",
    categoria: "Navegador",
    resumo: "O navegador do Ultron, agora no celular -- abas, busca embutida, mesmo visual do PC.",
    descricao:
      "Versão leve do RedCore do PC (gui/redcore.py): abas de verdade, barra de endereço que também " +
      "pesquisa no Google, voltar/avançar/recarregar. Favoritos, downloads, bloqueio de anúncios e aba " +
      "privada continuam exclusivos do RedCore do PC por enquanto -- este é o essencial, no bolso.",
    versaoNome: "1.0",
    versaoCodigo: 1,
    tamanhoMb: 5.3,
    requisito: "Android 8.0 ou superior",
    arquivo: "apps/redcore-mobile.apk",
    glifo: "R",
    atualizadoEm: "13/07/2026",
  },
];

function formatarTamanho(mb: number): string {
  return mb.toFixed(1).replace(".", ",") + " MB";
}

function criarCard(app: AppEntry): HTMLElement {
  const card = document.createElement("article");
  card.className = "app-card";
  card.id = app.id;

  card.innerHTML = `
    <div class="app-icon" data-categoria="${app.categoria}" aria-hidden="true">${app.glifo}</div>
    <div class="app-body">
      <div class="app-heading">
        <h2>${app.nome}</h2>
        <span class="app-category" data-categoria="${app.categoria}">${app.categoria}</span>
      </div>
      <p class="app-resumo">${app.resumo}</p>
      <dl class="app-meta">
        <div><dt>Versão</dt><dd>${app.versaoNome} <span class="dim">(build ${app.versaoCodigo})</span></dd></div>
        <div><dt>Tamanho</dt><dd>${formatarTamanho(app.tamanhoMb)}</dd></div>
        <div><dt>Requer</dt><dd>${app.requisito}</dd></div>
        <div><dt>Atualizado</dt><dd>${app.atualizadoEm}</dd></div>
      </dl>
      <p class="app-descricao">${app.descricao}</p>
      <a class="btn-instalar" href="${app.arquivo}" download>Baixar APK</a>
    </div>
  `;
  return card;
}

function render(): void {
  const lista = document.getElementById("catalogo");
  if (!lista) return;
  for (const app of CATALOGO) {
    lista.appendChild(criarCard(app));
  }

  const contador = document.getElementById("catalogo-contagem");
  if (contador) {
    contador.textContent = `${CATALOGO.length} app${CATALOGO.length === 1 ? "" : "s"} publicado${CATALOGO.length === 1 ? "" : "s"}`;
  }
}

document.addEventListener("DOMContentLoaded", render);
