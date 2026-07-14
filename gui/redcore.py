"""
gui/redcore.py
===============
RedCore: o navegador do próprio Ultron -- pedido explícito do usuário
(2026-07-06): "um navegador... pra o Ultron ter acesso a toda internet,
o próprio navegador dele que eu posso usar, e ele vê tudo que eu uso, e
pode apagar a memória dele".

É um navegador REAL (QtWebEngine -- Chromium embutido no Qt, já
disponível no ambiente, mesmo framework de todo o resto da GUI): abas,
barra de endereço, voltar/avançar/recarregar -- não um brinquedo, acessa
qualquer site que um navegador normal acessa.

Roda como processo PRÓPRIO e SEPARADO da janela principal do Ultron (não
tenta criar uma janela Qt dentro da QThread de outra QApplication --
isso quebraria; ver gui/app.py sobre por que widgets Qt só podem ser
manipulados na thread principal). "abre o redcore" (plugins/redcore.py)
só dá `subprocess.Popen([sys.executable, "-m", "gui.redcore", user_id])`,
igual abrir qualquer outro programa.

"Ele vê tudo que eu uso, incluindo e-mails" (pedido explícito, ainda
mais direto, 2026-07-06): cada navegação registra URL + título + TEXTO
VISÍVEL da página inteira (automacao/redcore_historico.py) -- não é só
metadado. Como webmail (Gmail/Outlook) costuma ser uma SPA que troca de
e-mail sem mudar a URL, cada aba também tira uma "foto" periódica do
texto (`_INTERVALO_CAPTURA_MS`), pra pegar o que você está lendo mesmo
sem navegação nova. Isso NÃO é o histórico interno do Chromium/Qt
(cookies, senhas, cache continuam onde sempre estiveram) -- é um
registro PRÓPRIO do Ultron, em texto puro no banco local. "Pode apagar
a memória dele": botão "🗑 Limpar histórico" na barra de ferramentas, e
o comando de chat "apaga o histórico do redcore" (plugins/redcore.py).
Abas PRIVADAS (🕵, ver `nova_aba(privada=True)`) são a única exceção
combinada: nada é registrado nesse histórico pra elas, de propósito.

Melhorias (pedido do usuário, "melhora o navegador"):
  - **Favoritos** (⭐, `automacao/redcore_favoritos.py`): marcar/
    desmarcar a página atual e reabrir depois, numa tabela própria do
    mesmo banco do histórico.
  - **Downloads**: qualquer download disparado pela navegação vai pra
    `data/redcore_downloads/` (nunca sobrescreve um arquivo existente,
    ver `_evitar_sobrescrever`) e aparece no botão "⬇ Downloads", com
    uma janela simples de progresso/lista.
  - **Busca na página** (Ctrl+F) e **atalhos de teclado** (Ctrl+T nova
    aba, Ctrl+W fecha aba, Ctrl+L foca endereço, Ctrl+R/F5 recarrega,
    Ctrl+D favorita, Ctrl+Shift+N aba privada, Ctrl+Shift+R modo
    leitura, Esc fecha a busca).
  - **Aba privada/anônima** (🕵): usa um `QWebEngineProfile` PRÓPRIO,
    fora do registro (off-the-record -- cookies/cache só em memória,
    somem ao fechar a aba) e nunca grava no histórico do RedCore.
  - **Shields, estilo Brave** (🛡, `_AdBlockInterceptor`): lista curada
    de domínios de publicidade/rastreamento conhecidos, bloqueados via
    `QWebEngineUrlRequestInterceptor` -- não é uma lista completa tipo
    EasyList, é o suficiente pra cortar o grosso da telemetria/anúncios
    sem depender de arquivo externo. O botão na barra mostra quantos
    rastreadores/anúncios foram bloqueados NESTA página (zera a cada
    navegação) e abre um painel com esse número, o total bloqueado
    desde sempre, e o interruptor de ligar/desligar (persiste em
    config.json -> redcore.bloqueio_anuncios) caso algum site quebre
    por causa disso.
  - **Modo leitura** (📖, `_JS_MODO_LEITURA`): injeta um `<style>` que
    esconde navegação/barras laterais/anúncios/comentários por
    heurística (seletores comuns, não é um algoritmo de extração de
    conteúdo tipo Readability) e recentraliza o texto numa coluna
    legível. Por aba, não persiste entre páginas (mesmo espírito do
    modo leitura de qualquer navegador de verdade: liga de novo se
    quiser em cada artigo).
  - **Nova aba (speed dial)** (`_gerar_html_nova_aba`): toda aba nova
    abre numa página local (não pede nada pra rede) com caixa de busca
    e a grade dos favoritos (automacao/redcore_favoritos.py), estilo
    Brave/Chrome -- não é uma navegação de verdade (sentinela
    `_PAGINA_INICIAL`, "redcore://home"), então não vira linha no
    histórico nem é favoritável.
"""

import html
import os
import sys
import time
import urllib.parse

from PySide6.QtCore import QUrl, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QTabWidget, QToolBar, QVBoxLayout, QWidget,
)
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

_PAGINA_INICIAL = "redcore://home"  # sentinela -- ver nova_aba() e _gerar_html_nova_aba
_INTERVALO_CAPTURA_MS = 20_000  # 20s -- frequente o bastante pra pegar troca de e-mail
_MIN_CONTEUDO_CHARS = 20  # ignora capturas triviais (tela em branco/carregando)
_DOWNLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "redcore_downloads"
)

# Heurística simples (não um extrator de conteúdo tipo Readability):
# esconde os elementos de clutter mais comuns por seletor de classe/id/tag
# e força o corpo numa coluna legível. `id` fixo no <style> pra dar pra
# remover de novo (alternar) sem precisar recarregar a página.
_JS_MODO_LEITURA = """
(function() {
  var id = 'ultron-modo-leitura';
  var existente = document.getElementById(id);
  if (existente) { existente.remove(); return false; }
  var style = document.createElement('style');
  style.id = id;
  style.textContent = `
    nav, header, footer, aside, iframe,
    [class*="sidebar" i], [class*="cookie" i], [class*="popup" i],
    [class*="modal" i], [class*="banner" i], [class*="newsletter" i],
    [class*="subscribe" i], [class*="related" i], [class*="recommend" i],
    [class*="comment" i], [class*="share" i], [class*="social" i],
    [class*="advert" i], [class*=" ad-" i], [class^="ad-" i],
    [id*="sidebar" i], [id*="comment" i], [role="banner"],
    [role="navigation"], [role="complementary"]
      { display: none !important; }
    html, body {
      max-width: 720px !important; margin: 0 auto !important; padding: 24px !important;
      font-family: Georgia, "Times New Roman", serif !important; font-size: 19px !important;
      line-height: 1.7 !important; background: #f7f2e9 !important; color: #222 !important;
    }
    body * { max-width: 100% !important; float: none !important; }
    img, video, figure { height: auto !important; }
  `;
  document.head.appendChild(style);
  return true;
})();
"""

# Lista curada (não é EasyList completa) de domínios de publicidade e
# rastreamento bem conhecidos -- suficiente pra cortar o grosso dos
# anúncios/telemetria de terceiros sem depender de baixar/atualizar uma
# lista externa. Desligável a qualquer momento pelo botão "🛡" caso
# algum site quebre por causa de um domínio bloqueado que ele precise.
_DOMINIOS_BLOQUEADOS = frozenset({
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "google-analytics.com",
    "googletagmanager.com", "googletagservices.com", "adservice.google.com",
    "adnxs.com", "adsrvr.org", "advertising.com", "taboola.com", "outbrain.com",
    "criteo.com", "criteo.net", "scorecardresearch.com", "quantserve.com", "quantcount.com",
    "moatads.com", "pubmatic.com", "rubiconproject.com", "openx.net", "media.net",
    "amazon-adsystem.com", "adform.net", "adroll.com", "bidswitch.net", "casalemedia.com",
    "contextweb.com", "districtm.io", "gumgum.com", "indexexchange.com", "lijit.com",
    "mathtag.com", "sharethrough.com", "smartadserver.com", "spotxchange.com", "teads.tv",
    "yieldmo.com", "zedo.com", "3lift.com", "adcolony.com", "applovin.com", "chartboost.com",
    "unityads.unity3d.com", "vungle.com", "mgid.com", "propellerads.com", "popads.net",
    "exoclick.com", "trafficjunky.com", "adsterra.com", "bidvertiser.com", "revcontent.com",
    "hotjar.com", "mixpanel.com", "fullstory.com", "mouseflow.com", "crazyegg.com",
    "clicktale.net", "analytics.tiktok.com", "ads-twitter.com",
    "bat.bing.com", "clarity.ms", "adjust.com", "kochava.com", "appsflyer.com",
    "doubleverify.com", "adsafeprotected.com", "serving-sys.com", "2mdn.net",
    "flashtalking.com", "tribalfusion.com", "adblade.com",
})

_ESTILO = """
QMainWindow, QWidget { background-color: #0c0505; }
QToolBar { background-color: #1b0f0f; border: none; padding: 4px; spacing: 6px; }
QLineEdit {
    background-color: #1b1010; color: #fbf9f9; border: 1px solid #382323;
    border-radius: 8px; padding: 6px 10px; font-size: 13px;
}
QLineEdit:focus { border: 1px solid #c22a1f; }
QPushButton {
    background-color: #241515; color: #e7e5e5; border: 1px solid #382323;
    border-radius: 8px; padding: 6px 10px;
}
QPushButton:hover { background-color: #351f1f; }
QPushButton:checked { background-color: #c22a1f; color: #fff; }
QTabWidget::pane { border: 1px solid #331c1c; }
QTabBar::tab {
    background-color: #1b0f0f; color: #c9baba; padding: 7px 14px;
    border: 1px solid #331c1c; border-bottom: none;
}
QTabBar::tab:selected { background-color: #261010; color: #ff5f52; }
QListWidget {
    background-color: #150b0b; color: #e7e5e5; border: 1px solid #382323; border-radius: 6px;
}
QListWidget::item:selected { background-color: #351f1f; }
QLabel { color: #c9baba; }
"""


def _gerar_html_nova_aba(user_id: str) -> str:
    """Nova aba estilo Brave/Chrome: caixa de busca + grade de favoritos
    (automacao/redcore_favoritos.py) renderizada localmente via
    `view.setHtml` (sem pedir nada pra rede -- ver nova_aba). Mantém a
    identidade visual vermelho/escuro do próprio Ultron (mesma paleta de
    _ESTILO) em vez de copiar as cores do Brave -- "interface do Brave"
    aqui é o PADRÃO de interação (busca + atalhos em grade), não uma
    repintura da marca."""
    from automacao import redcore_favoritos

    try:
        favoritos = redcore_favoritos.listar(user_id)
    except Exception:
        favoritos = []

    tiles = ""
    for f in favoritos[:12]:
        url = f["url"] or ""
        # Só http(s) -- automacao/redcore_favoritos.adicionar() já rejeita
        # qualquer outro esquema ao SALVAR, mas o filtro aqui é redundância
        # de propósito (defesa em profundidade): cobre favoritos que já
        # estavam no banco antes desse fix existir. Sem isso, um favorito
        # "javascript:..." viraria um <a href> clicável que executa script
        # na origem do navegador assim que a nova aba (speed dial) abrisse.
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        titulo = (f["titulo"] or "").strip() or urllib.parse.urlparse(url).netloc or url
        inicial = (urllib.parse.urlparse(url).netloc or titulo)[:1].upper() or "?"
        # html.escape protege contra um título/url de página que contenha
        # marcação HTML (a validação de esquema acima cuida do resto).
        tiles += f"""
        <a class="tile" href="{html.escape(url, quote=True)}" title="{html.escape(url, quote=True)}">
          <div class="tile-icone">{html.escape(inicial)}</div>
          <div class="tile-titulo">{html.escape(titulo[:26])}</div>
        </a>"""

    if not tiles:
        tiles = '<p class="vazio">Nenhum favorito ainda -- clique na ⭐ na barra de endereço pra ver os atalhos aqui.</p>'

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>Nova aba</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 32px;
    background: #0c0505; color: #fbf9f9;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  form {{ width: min(520px, 86vw); }}
  input[type="text"] {{
    width: 100%; padding: 14px 18px; font-size: 15px; border-radius: 24px;
    border: 1px solid #382323; background: #1b1010; color: #fbf9f9; outline: none;
  }}
  input[type="text"]:focus {{ border-color: #c22a1f; }}
  .grade {{
    display: grid; grid-template-columns: repeat(auto-fit, 96px); gap: 18px;
    justify-content: center; width: min(680px, 90vw);
  }}
  .tile {{
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    text-decoration: none; color: #e7e5e5; padding: 10px 4px;
    border-radius: 10px;
  }}
  .tile:hover {{ background: #1b0f0f; }}
  .tile-icone {{
    width: 44px; height: 44px; border-radius: 50%; background: #241515;
    border: 1px solid #382323; display: flex; align-items: center; justify-content: center;
    font-size: 17px; font-weight: 600; color: #ff5f52;
  }}
  .tile-titulo {{
    font-size: 12px; text-align: center; max-width: 92px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; color: #c9baba;
  }}
  .vazio {{ color: #8f7c7c; font-size: 13px; max-width: 320px; text-align: center; }}
  .marca {{ color: #c9baba; font-size: 22px; font-weight: 600; letter-spacing: 0.5px; }}
</style>
</head>
<body>
  <div class="marca">🔴 RedCore</div>
  <form action="https://www.google.com/search" method="GET">
    <input type="text" name="q" placeholder="Pesquisar ou digitar um endereço" autofocus>
  </form>
  <div class="grade">{tiles}</div>
</body>
</html>"""


def _evitar_sobrescrever(caminho: str) -> str:
    """Nunca sobrescreve um download existente -- acrescenta ' (N)'
    antes da extensão até achar um nome livre (mesmo padrão que
    navegadores comuns usam)."""
    if not os.path.exists(caminho):
        return caminho
    base, ext = os.path.splitext(caminho)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


class _AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    """Bloqueia requisições cujo host bate com `_DOMINIOS_BLOQUEADOS`
    (domínio exato ou subdomínio dele). `.ativo` liga/desliga em tempo
    real sem precisar recriar o interceptor.

    `bloqueado` (sinal Qt, não callback Python direto) avisa a janela
    principal sempre que algo é bloqueado -- `interceptRequest` roda na
    thread de rede do QtWebEngine, NUNCA na thread principal da GUI, e
    widgets Qt só podem ser tocados na thread principal. Um sinal Qt
    cruza threads em segurança sozinho (conexão em fila automática);
    chamar um callback Python comum aqui tocaria a UI da thread errada."""

    bloqueado = Signal(str)  # host da página (primeira parte) que originou o pedido bloqueado

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ativo = True

    def interceptRequest(self, info):
        if not self.ativo:
            return
        host = info.requestUrl().host().lower()
        if not host:
            return
        for dominio in _DOMINIOS_BLOQUEADOS:
            if host == dominio or host.endswith("." + dominio):
                info.block(True)
                pagina_host = info.firstPartyUrl().host().lower()
                if pagina_host:
                    self.bloqueado.emit(pagina_host)
                return


class RedCoreBrowser(QMainWindow):
    def __init__(self, user_id: str = "default_user"):
        super().__init__()
        self.user_id = user_id
        self.setWindowTitle("RedCore")
        self.resize(1200, 800)
        self.setStyleSheet(_ESTILO)

        self._downloads = []  # QWebEngineDownloadRequest desta sessão, mais recente primeiro
        self._private_profile = None  # criado sob demanda, ver _perfil_privado()

        from config.settings import get_settings
        self._interceptor = _AdBlockInterceptor(self)
        self._interceptor.ativo = bool(get_settings().get("redcore.bloqueio_anuncios", True))
        self._interceptor.bloqueado.connect(self._registrar_bloqueio)
        # Total de bloqueios desde sempre (Shields, estilo Brave) --
        # persistido em config.json, só escrito em disco com um
        # intervalo mínimo entre gravações (ver _registrar_bloqueio),
        # senão uma página com dezenas de rastreadores numa rajada só
        # deixaria isso lento à toa.
        self._bloqueios_totais = int(get_settings().get("redcore.bloqueios_totais", 0))
        self._ultimo_save_bloqueios = 0.0
        self._configurar_profile(QWebEngineProfile.defaultProfile())

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._fechar_aba)
        self.tabs.currentChanged.connect(self._aba_mudou)

        self._build_toolbar()
        self._build_central_widget()
        self._build_shortcuts()
        self.nova_aba(_PAGINA_INICIAL)

    # ---------- profiles (normal + privado) ----------

    def _configurar_profile(self, profile: QWebEngineProfile):
        profile.setUrlRequestInterceptor(self._interceptor)
        profile.downloadRequested.connect(self._download_requested)

    def _perfil_privado(self) -> QWebEngineProfile:
        """`QWebEngineProfile()` sem nome = perfil off-the-record (Qt
        cria automaticamente): cookies/cache só em memória, nunca tocam
        o disco e somem quando este processo do RedCore fecha."""
        if self._private_profile is None:
            self._private_profile = QWebEngineProfile(self)
            self._configurar_profile(self._private_profile)
        return self._private_profile

    # ---------- barra de ferramentas ----------

    def _build_toolbar(self):
        barra = QToolBar()
        barra.setMovable(False)
        self.addToolBar(barra)

        btn_voltar = QPushButton("←")
        btn_voltar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().back())
        barra.addWidget(btn_voltar)

        btn_avancar = QPushButton("→")
        btn_avancar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().forward())
        barra.addWidget(btn_avancar)

        btn_recarregar = QPushButton("⟳")
        btn_recarregar.clicked.connect(lambda: self._aba_atual() and self._aba_atual().reload())
        barra.addWidget(btn_recarregar)

        self.barra_endereco = QLineEdit()
        self.barra_endereco.setPlaceholderText("Digite um endereço ou pesquise...")
        self.barra_endereco.returnPressed.connect(self._navegar_da_barra)
        barra.addWidget(self.barra_endereco)

        self.btn_favoritar = QPushButton("☆")
        self.btn_favoritar.setToolTip("Favoritar esta página (Ctrl+D)")
        self.btn_favoritar.clicked.connect(self._alternar_favorito)
        barra.addWidget(self.btn_favoritar)

        btn_nova_aba = QPushButton("+ Aba")
        btn_nova_aba.clicked.connect(lambda: self.nova_aba(_PAGINA_INICIAL))
        barra.addWidget(btn_nova_aba)

        btn_privada = QPushButton("🕵 Privada")
        btn_privada.setToolTip("Nova aba privada (Ctrl+Shift+N) -- não fica no histórico")
        btn_privada.clicked.connect(lambda: self.nova_aba(_PAGINA_INICIAL, privada=True))
        barra.addWidget(btn_privada)

        btn_favoritos = QPushButton("☰ Favoritos")
        btn_favoritos.clicked.connect(self._abrir_favoritos)
        barra.addWidget(btn_favoritos)

        self.btn_downloads = QPushButton("⬇ Downloads")
        self.btn_downloads.clicked.connect(self._abrir_downloads)
        barra.addWidget(self.btn_downloads)

        btn_busca = QPushButton("🔎")
        btn_busca.setToolTip("Buscar na página (Ctrl+F)")
        btn_busca.clicked.connect(self._alternar_busca)
        barra.addWidget(btn_busca)

        self.btn_shields = QPushButton("🛡")
        self.btn_shields.setToolTip("Shields -- rastreadores/anúncios bloqueados nesta página (clique pra ver detalhes)")
        self.btn_shields.clicked.connect(self._abrir_shields)
        barra.addWidget(self.btn_shields)

        self.btn_leitura = QPushButton("📖")
        self.btn_leitura.setToolTip("Modo leitura -- limpa o clutter da página (por aba, some ao navegar)")
        self.btn_leitura.setCheckable(True)
        self.btn_leitura.toggled.connect(self._alternar_modo_leitura)
        barra.addWidget(self.btn_leitura)

        btn_limpar = QPushButton("🗑 Limpar histórico")
        btn_limpar.clicked.connect(self._limpar_historico)
        barra.addWidget(btn_limpar)

    # ---------- busca na página ----------

    def _build_central_widget(self):
        """Envolve as abas numa barra de busca (Ctrl+F) que fica
        escondida por padrão -- ver _alternar_busca()."""
        self.barra_busca_widget = QWidget()
        layout_busca = QHBoxLayout(self.barra_busca_widget)
        layout_busca.setContentsMargins(6, 4, 6, 4)

        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText("Buscar na página...")
        self.campo_busca.textChanged.connect(lambda _t: self._buscar_na_pagina())
        self.campo_busca.returnPressed.connect(lambda: self._buscar_na_pagina())
        layout_busca.addWidget(self.campo_busca)

        btn_anterior = QPushButton("▲")
        btn_anterior.clicked.connect(lambda: self._buscar_na_pagina(voltar=True))
        layout_busca.addWidget(btn_anterior)

        btn_proximo = QPushButton("▼")
        btn_proximo.clicked.connect(lambda: self._buscar_na_pagina())
        layout_busca.addWidget(btn_proximo)

        btn_fechar = QPushButton("✕")
        btn_fechar.clicked.connect(self._fechar_busca)
        layout_busca.addWidget(btn_fechar)

        self.barra_busca_widget.setVisible(False)

        central = QWidget()
        layout_central = QVBoxLayout(central)
        layout_central.setContentsMargins(0, 0, 0, 0)
        layout_central.setSpacing(0)
        layout_central.addWidget(self.barra_busca_widget)
        layout_central.addWidget(self.tabs)
        self.setCentralWidget(central)

    def _alternar_busca(self):
        if self.barra_busca_widget.isVisible():
            self._fechar_busca()
            return
        self.barra_busca_widget.setVisible(True)
        self.campo_busca.setFocus()
        self.campo_busca.selectAll()

    def _fechar_busca(self):
        self.barra_busca_widget.setVisible(False)
        aba = self._aba_atual()
        if aba is not None:
            aba.findText("")  # limpa o destaque da busca anterior
        self.tabs.setFocus()

    def _buscar_na_pagina(self, voltar: bool = False):
        aba = self._aba_atual()
        if aba is None:
            return
        texto = self.campo_busca.text()
        if not texto:
            aba.findText("")
            return
        if voltar:
            aba.findText(texto, QWebEnginePage.FindFlag.FindBackward)
        else:
            aba.findText(texto)

    # ---------- atalhos de teclado ----------

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(lambda: self.nova_aba(_PAGINA_INICIAL))
        QShortcut(QKeySequence("Ctrl+Shift+N"), self).activated.connect(
            lambda: self.nova_aba(_PAGINA_INICIAL, privada=True)
        )
        QShortcut(QKeySequence("Ctrl+W"), self).activated.connect(self._fechar_aba_atual)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._focar_endereco)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(
            lambda: self._aba_atual() and self._aba_atual().reload()
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(
            lambda: self._aba_atual() and self._aba_atual().reload()
        )
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._alternar_busca)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._alternar_favorito)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self).activated.connect(self.btn_leitura.toggle)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._fechar_busca)

    def _fechar_aba_atual(self):
        indice = self.tabs.currentIndex()
        if indice != -1:
            self._fechar_aba(indice)

    def _focar_endereco(self):
        self.barra_endereco.setFocus()
        self.barra_endereco.selectAll()

    # ---------- abas ----------

    def _aba_atual(self) -> QWebEngineView:
        return self.tabs.currentWidget()

    def nova_aba(self, url: str, privada: bool = False):
        view = QWebEngineView()
        if privada:
            view.setPage(QWebEnginePage(self._perfil_privado(), view))
        view._privada = privada       # nunca grava no histórico do RedCore, ver _url_mudou/_pagina_carregou
        view._visita_id = -1          # id da linha do histórico da visita atual (redcore_historico)
        view._ultimo_conteudo = None  # último texto capturado -- evita logar a mesma coisa de novo
        view._modo_leitura = False    # por aba -- ver _alternar_modo_leitura
        view._bloqueios_pagina = 0    # por aba -- ver _registrar_bloqueio (Shields, estilo Brave)
        if url == _PAGINA_INICIAL:
            # Nova aba (speed dial): renderizada localmente, não é uma
            # navegação de verdade -- não passa por load()/_url_mudou,
            # então não vira linha de histórico nem tenta resolver DNS.
            view.setHtml(_gerar_html_nova_aba(self.user_id), QUrl(_PAGINA_INICIAL))
        else:
            view.load(QUrl(url))
        indice = self.tabs.addTab(view, "🕵 Nova aba privada" if privada else "Nova aba")
        self.tabs.setCurrentIndex(indice)

        view.titleChanged.connect(lambda titulo, v=view: self._titulo_mudou(v, titulo))
        view.urlChanged.connect(lambda qurl, v=view: self._url_mudou(v, qurl))
        view.loadFinished.connect(lambda ok, v=view: self._pagina_carregou(v, ok))

        # Captura periódica -- pega conteúdo que muda SEM navegação nova
        # (trocar de e-mail numa SPA como Gmail/Outlook não muda a URL).
        # Abas privadas também rodam o timer (é inofensivo), mas
        # _capturar_conteudo_periodico ignora abas privadas na prática.
        timer = QTimer(self)
        timer.setInterval(_INTERVALO_CAPTURA_MS)
        timer.timeout.connect(lambda v=view: self._capturar_conteudo_periodico(v))
        timer.start()
        view._timer_captura = timer  # guarda referência (senão o GC do Python pode coletar o timer)
        return view

    def _fechar_aba(self, indice: int):
        widget = self.tabs.widget(indice)
        if widget is not None and hasattr(widget, "_timer_captura"):
            widget._timer_captura.stop()
        self.tabs.removeTab(indice)
        if widget:
            widget.deleteLater()
        if self.tabs.count() == 0:
            self.close()

    def _aba_mudou(self, _indice: int):
        aba = self._aba_atual()
        if aba is not None:
            url = aba.url().toString()
            self.barra_endereco.setText("" if url == _PAGINA_INICIAL else url)
        # blockSignals evita reentrar em _alternar_modo_leitura (que agiria
        # na aba ERRADA -- ele sempre opera na aba "atual" no momento do
        # toggle, e aqui só queremos REFLETIR o estado, não mudar nada).
        self.btn_leitura.blockSignals(True)
        self.btn_leitura.setChecked(bool(aba is not None and getattr(aba, "_modo_leitura", False)))
        self.btn_leitura.blockSignals(False)
        self._atualizar_badge_shields()
        self._atualizar_estado_favorito()

    def _titulo_mudou(self, view: QWebEngineView, titulo: str):
        indice = self.tabs.indexOf(view)
        if indice == -1:
            return
        texto = (titulo[:24] + "…") if len(titulo) > 24 else (titulo or "Nova aba")
        prefixo = "🕵 " if getattr(view, "_privada", False) else ""
        self.tabs.setTabText(indice, prefixo + texto)

    def _url_mudou(self, view: QWebEngineView, qurl: QUrl):
        url = qurl.toString()
        # Navegação nova sempre desliga o modo leitura desta aba (mesmo
        # comportamento de qualquer navegador de verdade -- não faz
        # sentido persistir o CSS injetado de uma página na próxima), e
        # zera a contagem de bloqueios (Shields, estilo Brave, mostra o
        # bloqueado NESTA página, não um total acumulado pra sempre).
        view._modo_leitura = False
        view._bloqueios_pagina = 0
        if view is self._aba_atual():
            self.barra_endereco.setText("" if url == _PAGINA_INICIAL else url)
            self._atualizar_estado_favorito()
            self.btn_leitura.blockSignals(True)
            self.btn_leitura.setChecked(False)
            self.btn_leitura.blockSignals(False)
            self._atualizar_badge_shields()
        view._ultimo_conteudo = None
        # Nova aba (speed dial) não é uma navegação de verdade -- não
        # grava história nenhuma, mesma lógica de aba privada.
        if getattr(view, "_privada", False) or url == _PAGINA_INICIAL:
            view._visita_id = -1
            return
        # Navegação nova de verdade -- abre uma linha NOVA no histórico
        # (o conteúdo/título ainda vão chegar via loadFinished/titleChanged,
        # ver atualizar_conteudo) e reseta o "último conteúdo visto" pra
        # não confundir com o da página anterior nesta mesma aba.
        from automacao import redcore_historico
        try:
            view._visita_id = redcore_historico.registrar_visita(self.user_id, url, view.title())
        except Exception:
            view._visita_id = -1

    def _pagina_carregou(self, view: QWebEngineView, ok: bool):
        if not ok or view is None or getattr(view, "_privada", False):
            return

        def _recebeu_texto(texto, v=view):
            if not texto:
                return
            v._ultimo_conteudo = texto
            from automacao import redcore_historico
            try:
                redcore_historico.atualizar_conteudo(
                    getattr(v, "_visita_id", -1), titulo=v.title(), conteudo=texto,
                )
            except Exception:
                pass

        try:
            view.page().toPlainText(_recebeu_texto)
        except Exception:
            pass

    def _capturar_conteudo_periodico(self, view: QWebEngineView):
        """Roda a cada _INTERVALO_CAPTURA_MS por aba -- pega o texto
        atual e, se for DIFERENTE do último capturado (ex.: você trocou
        de e-mail numa SPA sem a URL mudar), registra como uma visita
        NOVA (é conteúdo novo que você olhou, merece linha própria no
        histórico, não só sobrescrever a mesma). Nunca roda pra abas
        privadas nem pra nova aba (speed dial, não é navegação real)."""
        try:
            if (
                view is None or not view.isVisible() or getattr(view, "_privada", False)
                or view.url().toString() == _PAGINA_INICIAL
            ):
                return
        except RuntimeError:
            return  # widget C++ já destruído (aba fechada); o timer some no próximo _fechar_aba

        def _recebeu_texto(texto, v=view):
            anterior = getattr(v, "_ultimo_conteudo", None)
            if not texto or len(texto.strip()) < _MIN_CONTEUDO_CHARS or texto == anterior:
                return
            v._ultimo_conteudo = texto
            from automacao import redcore_historico
            try:
                v._visita_id = redcore_historico.registrar_visita(
                    self.user_id, v.url().toString(), v.title(), texto,
                )
            except Exception:
                pass

        try:
            view.page().toPlainText(_recebeu_texto)
        except Exception:
            pass

    # ---------- barra de endereço ----------

    def _navegar_da_barra(self):
        texto = self.barra_endereco.text().strip()
        if not texto:
            return
        aba = self._aba_atual()
        if aba is None:
            aba = self.nova_aba(_PAGINA_INICIAL)
        aba.load(QUrl(_resolver_endereco(texto)))

    # ---------- favoritos ----------

    def _atualizar_estado_favorito(self):
        from automacao import redcore_favoritos
        aba = self._aba_atual()
        if aba is None:
            return
        url = aba.url().toString()
        favoritado = (
            bool(url) and url not in ("about:blank", _PAGINA_INICIAL)
            and redcore_favoritos.esta_favoritado(self.user_id, url)
        )
        self.btn_favoritar.setText("⭐" if favoritado else "☆")
        self.btn_favoritar.setChecked(favoritado)

    def _alternar_favorito(self):
        from automacao import redcore_favoritos
        aba = self._aba_atual()
        if aba is None:
            return
        url = aba.url().toString()
        if not url or url in ("about:blank", _PAGINA_INICIAL):
            return
        if redcore_favoritos.esta_favoritado(self.user_id, url):
            redcore_favoritos.remover(self.user_id, url)
            self._notificar("Removido dos favoritos.")
        else:
            redcore_favoritos.adicionar(self.user_id, url, aba.title())
            self._notificar("Adicionado aos favoritos.")
        self._atualizar_estado_favorito()

    def _abrir_favoritos(self):
        from automacao import redcore_favoritos
        favoritos = redcore_favoritos.listar(self.user_id)

        dialogo = QDialog(self)
        dialogo.setWindowTitle("Favoritos do RedCore")
        dialogo.setStyleSheet(_ESTILO)
        dialogo.resize(480, 320)
        layout = QVBoxLayout(dialogo)

        if not favoritos:
            layout.addWidget(QLabel("Nenhum favorito ainda -- clique na ⭐ pra favoritar a página atual."))

        lista = QListWidget()
        for f in favoritos:
            item = QListWidgetItem(f["titulo"] or f["url"])
            item.setData(Qt.ItemDataRole.UserRole, f["url"])
            lista.addItem(item)
        layout.addWidget(lista)

        def _abrir_selecionado():
            item = lista.currentItem()
            if not item:
                return
            url = item.data(Qt.ItemDataRole.UserRole)
            # Defesa em profundidade -- automacao/redcore_favoritos.adicionar
            # já rejeita esquemas fora de http(s) ao salvar, mas isso cobre
            # um favorito ruim ("javascript:...") que já estivesse no banco
            # de antes desse fix: aba.load(QUrl(...)) executaria o script
            # na origem da página carregada na aba atual.
            if not (url.startswith("http://") or url.startswith("https://")):
                self._notificar("Favorito com endereço inválido -- remova-o.")
                return
            aba = self._aba_atual() or self.nova_aba(_PAGINA_INICIAL)
            aba.load(QUrl(url))
            dialogo.accept()

        def _remover_selecionado():
            item = lista.currentItem()
            if not item:
                return
            url = item.data(Qt.ItemDataRole.UserRole)
            redcore_favoritos.remover(self.user_id, url)
            lista.takeItem(lista.row(item))
            self._atualizar_estado_favorito()

        lista.itemDoubleClicked.connect(lambda _i: _abrir_selecionado())

        linha_botoes = QHBoxLayout()
        btn_abrir = QPushButton("Abrir")
        btn_abrir.clicked.connect(_abrir_selecionado)
        linha_botoes.addWidget(btn_abrir)
        btn_remover = QPushButton("Remover")
        btn_remover.clicked.connect(_remover_selecionado)
        linha_botoes.addWidget(btn_remover)
        layout.addLayout(linha_botoes)

        dialogo.exec()

    # ---------- downloads ----------

    def _download_requested(self, download: QWebEngineDownloadRequest):
        os.makedirs(_DOWNLOADS_DIR, exist_ok=True)
        nome_sugerido = download.downloadFileName() or "arquivo_baixado"
        caminho = _evitar_sobrescrever(os.path.join(_DOWNLOADS_DIR, nome_sugerido))
        download.setDownloadDirectory(os.path.dirname(caminho))
        download.setDownloadFileName(os.path.basename(caminho))
        download.accept()

        self._downloads.insert(0, download)
        download.isFinishedChanged.connect(self._atualizar_botao_downloads)
        download.receivedBytesChanged.connect(self._atualizar_botao_downloads)
        self._atualizar_botao_downloads()
        self._notificar(f"Baixando: {os.path.basename(caminho)}")

    def _atualizar_botao_downloads(self):
        em_andamento = sum(1 for d in self._downloads if not d.isFinished())
        if em_andamento:
            self.btn_downloads.setText(f"⬇ Downloads ({em_andamento})")
        else:
            self.btn_downloads.setText("⬇ Downloads")

    def _texto_download(self, d: QWebEngineDownloadRequest) -> str:
        nome = d.downloadFileName()
        if d.isFinished():
            concluido = d.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
            estado = "concluído" if concluido else "cancelado/interrompido"
        else:
            total = d.totalBytes()
            pct = int(100 * d.receivedBytes() / total) if total > 0 else 0
            estado = f"baixando {pct}%"
        return f"{nome} -- {estado}"

    def _abrir_no_explorador(self, caminho: str):
        try:
            pasta = os.path.dirname(caminho)
            if sys.platform == "win32":
                os.startfile(pasta)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", pasta])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            QMessageBox.warning(self, "RedCore", f"Não consegui abrir a pasta: {e}")

    def _abrir_downloads(self):
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Downloads do RedCore")
        dialogo.setStyleSheet(_ESTILO)
        dialogo.resize(480, 320)
        layout = QVBoxLayout(dialogo)

        if not self._downloads:
            layout.addWidget(QLabel("Nenhum download nesta sessão ainda."))

        lista = QListWidget()
        for d in self._downloads:
            item = QListWidgetItem(self._texto_download(d))
            item.setData(Qt.ItemDataRole.UserRole, d)
            lista.addItem(item)
        layout.addWidget(lista)

        def _abrir_pasta_selecionada():
            item = lista.currentItem()
            if not item:
                return
            d = item.data(Qt.ItemDataRole.UserRole)
            self._abrir_no_explorador(os.path.join(d.downloadDirectory(), d.downloadFileName()))

        lista.itemDoubleClicked.connect(lambda _i: _abrir_pasta_selecionada())
        btn_abrir = QPushButton("Abrir pasta")
        btn_abrir.clicked.connect(_abrir_pasta_selecionada)
        layout.addWidget(btn_abrir)

        dialogo.exec()

    # ---------- Shields (bloqueio de anúncios), estilo Brave ----------

    def _registrar_bloqueio(self, pagina_host: str):
        """Conectado ao sinal `_AdBlockInterceptor.bloqueado` -- roda na
        THREAD PRINCIPAL (o sinal Qt já cruzou da thread de rede pra cá
        em segurança), pode mexer em widget à vontade. Credita a
        contagem "nesta página" de toda aba cuja URL atual bate com o
        host que originou o pedido bloqueado (normalmente uma só, mas
        duas abas na mesma página contam as duas -- aproximação
        razoável, o interceptor é compartilhado entre todas as abas)."""
        self._bloqueios_totais += 1
        agora = time.time()
        if agora - self._ultimo_save_bloqueios > 2.0:
            self._ultimo_save_bloqueios = agora
            from config.settings import get_settings
            settings = get_settings()
            settings.set("redcore.bloqueios_totais", self._bloqueios_totais)
            settings.save()
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if view is None:
                continue
            url_aba = view.url().host().lower()
            if url_aba and (
                url_aba == pagina_host
                or pagina_host.endswith("." + url_aba)
                or url_aba.endswith("." + pagina_host)
            ):
                view._bloqueios_pagina = getattr(view, "_bloqueios_pagina", 0) + 1
        self._atualizar_badge_shields()

    def _atualizar_badge_shields(self):
        aba = self._aba_atual()
        n = getattr(aba, "_bloqueios_pagina", 0) if aba is not None else 0
        self.btn_shields.setText(f"🛡 {n}" if n else "🛡")

    def _abrir_shields(self):
        """Painel "Shields", estilo Brave: quanto foi bloqueado NESTA
        página, o total desde sempre, e o interruptor de ligar/desligar
        (antes um botão separado na barra -- agora mora aqui, junto com
        os números que dão contexto pra decisão)."""
        aba = self._aba_atual()
        host_atual = aba.url().host() if aba is not None else ""
        bloqueios_pagina = getattr(aba, "_bloqueios_pagina", 0) if aba is not None else 0

        dialogo = QDialog(self)
        dialogo.setWindowTitle("Shields")
        layout = QVBoxLayout(dialogo)

        titulo = QLabel(f"🛡 Shields{f' para {host_atual}' if host_atual else ''}")
        titulo.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(titulo)

        layout.addWidget(QLabel(f"{bloqueios_pagina} rastreador(es)/anúncio(s) bloqueado(s) nesta página."))
        layout.addWidget(QLabel(f"{self._bloqueios_totais} bloqueado(s) ao todo, desde sempre."))

        chk_ligado = QCheckBox("Bloqueio de anúncios/rastreadores ligado")
        chk_ligado.setChecked(self._interceptor.ativo)
        chk_ligado.toggled.connect(self._alternar_bloqueio)
        layout.addWidget(chk_ligado)

        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(dialogo.accept)
        layout.addWidget(btn_fechar)

        dialogo.exec()

    def _alternar_bloqueio(self, ligado: bool):
        self._interceptor.ativo = ligado
        from config.settings import get_settings
        settings = get_settings()
        settings.set("redcore.bloqueio_anuncios", ligado)
        settings.save()
        self._notificar("Bloqueio de anúncios ligado." if ligado else "Bloqueio de anúncios desligado.")

    # ---------- modo leitura ----------

    def _alternar_modo_leitura(self, ligado: bool):
        aba = self._aba_atual()
        if aba is None:
            return
        # _JS_MODO_LEITURA já alterna sozinho (remove o <style> se já
        # existir) -- `ligado` aqui é só o estado do BOTÃO, sincronizamos
        # `_modo_leitura` da aba com o retorno real do JS injetado.
        def _apos_alternar(ativo: bool, view=aba):
            view._modo_leitura = bool(ativo)
            if view is self._aba_atual():
                self.btn_leitura.blockSignals(True)
                self.btn_leitura.setChecked(bool(ativo))
                self.btn_leitura.blockSignals(False)

        aba.page().runJavaScript(_JS_MODO_LEITURA, _apos_alternar)

    # ---------- notificações discretas ----------

    def _notificar(self, texto: str, ms: int = 4000):
        self.statusBar().showMessage(texto, ms)

    # ---------- histórico ----------

    def _limpar_historico(self):
        resp = QMessageBox.question(
            self, "Limpar histórico do RedCore",
            "Isso apaga TUDO que o Ultron registrou (URLs, títulos e o texto das páginas vistas, "
            "incluindo e-mails abertos). Não afeta cookies, senhas salvas, downloads ou favoritos. "
            "Confirma?",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        from automacao import redcore_historico
        total = redcore_historico.limpar_historico(self.user_id)
        QMessageBox.information(self, "Histórico limpo", f"{total} visita(s) removida(s) da memória do Ultron.")

    def closeEvent(self, event):
        # Rede de segurança pro total de bloqueios (Shields) -- as
        # gravações normais são throttladas (ver _registrar_bloqueio),
        # então até uns 2s de contagem podiam se perder se a janela
        # fechasse bem no meio de uma rajada de bloqueios.
        from config.settings import get_settings
        settings = get_settings()
        settings.set("redcore.bloqueios_totais", self._bloqueios_totais)
        settings.save()
        super().closeEvent(event)


def _resolver_endereco(texto: str) -> str:
    """Trata a barra de endereço como um navegador de verdade trata:
    URL direta se parecer com uma, senão pesquisa."""
    if texto.startswith("http://") or texto.startswith("https://"):
        return texto
    if "." in texto and " " not in texto:
        return f"https://{texto}"
    return f"https://www.google.com/search?q={urllib.parse.quote(texto)}"


def run_redcore(user_id: str = "default_user"):
    """Sempre roda como processo PRÓPRIO (ver docstring do módulo) --
    por isso sempre cria a QApplication e o loop de eventos aqui, sem
    tentar reaproveitar uma instância existente de outro processo (isso
    não seria possível entre processos separados de qualquer forma)."""
    app = QApplication(sys.argv)
    janela = RedCoreBrowser(user_id)
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _user_id = sys.argv[1] if len(sys.argv) > 1 else "default_user"
    run_redcore(_user_id)
