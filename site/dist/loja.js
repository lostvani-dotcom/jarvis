"use strict";
/**
 * site/src/loja.ts
 * ===================
 * Catálogo da loja -- cada app criado vira um item nesta lista e a
 * página se desenha sozinha a partir dela (ver `render()`). Adicionar
 * um novo app no futuro é só adicionar um objeto em `CATALOGO`, nada
 * de mexer no HTML.
 */
const CATALOGO = [
    {
        id: "ultron-companion",
        nome: "Ultron Companion",
        categoria: "Produtividade",
        resumo: "O Ultron no seu bolso -- interface de chat estilo ChatGPT, controla o celular e conversa com o núcleo do PC pela Wi-Fi.",
        descricao: "Chat com o Ultron direto do celular (bolhas de mensagem, campo em pílula, histórico de " +
            "conversas num painel deslizante estilo ChatGPT -- configuração de conexão/permissões numa " +
            "tela própria, atrás do ícone ⚙), encaminha notificações (Instagram/WhatsApp/Telegram/" +
            "Signal/Discord) e responde comandos do aparelho (bateria, lanterna, volume, alarme, " +
            "localização e mais) mesmo com o app fechado. Grava amostra de voz pelo microfone do " +
            "celular (pra clonagem de voz) e identifica rostos cadastrados usando a câmera do celular " +
            "-- os dois processados pelo Ultron do PC. Tela do PC ao vivo (\"Ver a tela do PC\"), " +
            "atalho de hardware (3 toques no volume abrem o app já ouvindo, via Acessibilidade) e um " +
            "painel de estatísticas de uso. Agora também: um widget pra tela inicial (status + " +
            "microfone de um toque), \"Compartilhar\" de qualquer app manda o texto/link direto pro " +
            "Ultron, e as conversas salvas podem ser exportadas/compartilhadas como texto. Boa parte " +
            "das funções roda 100% offline no próprio celular. Modo nuvem (conversar sem o PC ligado) " +
            "com memória persistente e sincronização automática em segundo plano -- conversa aberta " +
            "com acesso à memória/base de conhecimento completa continua exigindo o Ultron do PC na " +
            "mesma rede.",
        versaoNome: "2.0",
        versaoCodigo: 12,
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
        descricao: "App dedicado só a isso: procurar o Ultron na Wi-Fi de casa, listar o catálogo publicado por ele " +
            "(GET /loja/catalogo) e baixar/instalar qualquer app da lista -- sem loja de terceiros, sem conta, " +
            "sem rastreamento. O mesmo catálogo que alimenta esta página também alimenta o app. Agora a " +
            "própria Loja se atualiza sozinha quando publicamos uma versão nova dela.",
        versaoNome: "1.1",
        versaoCodigo: 2,
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
        resumo: "O navegador do Ultron, agora no celular -- abas, busca embutida, modo leitura, favoritos sincronizados com o PC, bloqueio de anúncios.",
        descricao: "Versão leve do RedCore do PC (gui/redcore.py): abas de verdade, barra de endereço que também " +
            "pesquisa no Google, voltar/avançar/recarregar, bloqueio de anúncios/rastreadores (menu ⋮, " +
            "mesma lista de domínios do desktop), modo leitura (limpa o clutter de artigos) e favoritos " +
            "sincronizados com o RedCore do PC nos dois sentidos. Também sincroniza o histórico de " +
            "navegação com o Ultron do PC, mas só se você ligar essa opção nas configurações -- desligado " +
            "por padrão. Aba privada continua exclusiva do RedCore do PC por enquanto.",
        versaoNome: "1.3",
        versaoCodigo: 4,
        tamanhoMb: 5.4,
        requisito: "Android 8.0 ou superior",
        arquivo: "apps/redcore-mobile.apk",
        glifo: "R",
        atualizadoEm: "13/07/2026",
    },
];
function formatarTamanho(mb) {
    return mb.toFixed(1).replace(".", ",") + " MB";
}
function criarCard(app, indice) {
    const card = document.createElement("article");
    card.className = "app-card glow-surface";
    card.id = app.id;
    card.dataset.reveal = "";
    // Escalona a entrada de cada card (ver [data-reveal] em style.css,
    // compartilhado com o dossiê) -- sem isso todos os cards apareceriam
    // de uma vez só, menos vivo que um pra cada.
    card.style.setProperty("--reveal-delay", `${indice * 0.08}s`);
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
function render() {
    const lista = document.getElementById("catalogo");
    if (!lista)
        return;
    CATALOGO.forEach((app, indice) => {
        lista.appendChild(criarCard(app, indice));
    });
    const contador = document.getElementById("catalogo-contagem");
    if (contador) {
        contador.textContent = `${CATALOGO.length} app${CATALOGO.length === 1 ? "" : "s"} publicado${CATALOGO.length === 1 ? "" : "s"}`;
    }
    // Só agora os cards existem de verdade no DOM -- chamar isso antes
    // (ex.: direto no DOMContentLoaded de interactions.ts) não acharia
    // nenhum ".app-card" pra observar/animar (ver interactions.ts).
    initScrollReveal();
    initGlowSurfaces();
}
document.addEventListener("DOMContentLoaded", render);
//# sourceMappingURL=loja.js.map