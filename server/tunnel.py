"""
server/tunnel.py
===================
Acesso remoto (fora da rede local) ao servidor do Ultron
(server/http_server.py) via um túnel HTTPS do Cloudflare (`cloudflared`)
-- não abre porta nenhuma no roteador, e nunca expõe o servidor HTTP em
texto puro pra internet (o Cloudflare termina o TLS na borda; o túnel
até aqui já sai criptografado). O Bearer token (server/http_server.py:
get_or_create_token(), gerado com secrets.token_urlsafe) continua sendo
a autenticação de verdade -- o túnel só resolve o "como alcançar o PC
de fora de casa", não substitui o token.

Usa um "quick tunnel" (`cloudflared tunnel --url http://localhost:<porta>`):
zero configuração, zero conta Cloudflare necessária -- mas a URL gerada
(https://xxxx.trycloudflare.com) muda toda vez que reinicia. Pra uma
URL fixa que nunca muda, é preciso um túnel NOMEADO (conta Cloudflare +
domínio próprio) -- configuração manual única, fora do escopo deste
arquivo (ver server/README.md pro passo a passo).

O binário `cloudflared` é baixado uma vez (~30MB) pra tools/, igual ao
resto do toolchain externo do projeto (ver dispositivos/README.md pro
Android SDK) -- não é uma dependência Python, então não entra em
requirements*.txt.
"""

import os
import platform
import re
import subprocess
import sys
import threading
import urllib.request

from logs.logger import get_logger

log = get_logger("server")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")

_CLOUDFLARED_URL_WINDOWS = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)

_processo = None
_url_atual = {"url": None}
_lock = threading.Lock()


def _caminho_binario() -> str:
    nome = "cloudflared.exe" if platform.system() == "Windows" else "cloudflared"
    return os.path.join(TOOLS_DIR, nome)


def disponivel() -> bool:
    return os.path.isfile(_caminho_binario())


def baixar_cloudflared() -> str:
    """Baixa o binário do cloudflared pra tools/, se ainda não tiver.
    Download automático só implementado pro Windows (mesma plataforma
    do resto do projeto) -- nos demais, pede pra baixar manualmente."""
    caminho = _caminho_binario()
    if os.path.isfile(caminho):
        return caminho
    if platform.system() != "Windows":
        raise RuntimeError(
            "Download automático do cloudflared só implementado pro Windows por "
            "enquanto -- baixe manualmente em "
            "https://github.com/cloudflare/cloudflared/releases e salve em "
            f"{caminho}."
        )
    os.makedirs(TOOLS_DIR, exist_ok=True)
    log.info("baixando cloudflared de %s ...", _CLOUDFLARED_URL_WINDOWS)
    urllib.request.urlretrieve(_CLOUDFLARED_URL_WINDOWS, caminho)
    return caminho


def url_atual():
    return _url_atual["url"]


def tunel_ativo() -> bool:
    return _processo is not None and _processo.poll() is None


def iniciar_tunel(porta: int, timeout: float = 25.0) -> str:
    """Inicia um quick tunnel apontando pra http://localhost:<porta> e
    devolve a URL pública assim que ela aparecer na saída do processo
    (https://xxxx.trycloudflare.com). Mantém o processo rodando em
    segundo plano até parar_tunel() ser chamado ou o Ultron encerrar."""
    global _processo
    with _lock:
        if tunel_ativo() and _url_atual["url"]:
            return _url_atual["url"]

        caminho = baixar_cloudflared()
        _url_atual["url"] = None

        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _processo = subprocess.Popen(
            [caminho, "tunnel", "--url", f"http://localhost:{porta}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs,
        )

        padrao_url = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")
        evento_pronto = threading.Event()

        def _ler_saida():
            for linha in _processo.stdout:
                log.info("[cloudflared] %s", linha.strip())
                if _url_atual["url"] is None:
                    m = padrao_url.search(linha)
                    if m:
                        _url_atual["url"] = m.group(0)
                        evento_pronto.set()

        threading.Thread(target=_ler_saida, daemon=True).start()

    if not evento_pronto.wait(timeout=timeout):
        raise RuntimeError(
            "Túnel não respondeu a tempo -- veja logs/jarvis.log (categoria 'server') pra detalhes."
        )
    return _url_atual["url"]


def parar_tunel():
    global _processo
    with _lock:
        if _processo is not None:
            _processo.terminate()
            _processo = None
        _url_atual["url"] = None
