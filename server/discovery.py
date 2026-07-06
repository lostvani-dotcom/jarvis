"""
server/discovery.py
======================
Descoberta automática do Ultron na rede local via UDP broadcast --
assim o app do celular (app_android/) acha o IP do PC e conecta
sozinho, sem precisar digitar IP nem token.

Decisão consciente de segurança (pedida explicitamente pelo usuário
depois que copiar o token manualmente causou fricção demais na
prática): a resposta de descoberta INCLUI o token. Isso significa que
qualquer aparelho capaz de mandar um broadcast UDP na mesma rede
Wi-Fi consegue descobrir e usar o Ultron -- o perímetro de confiança
passa a ser "estar na minha rede Wi-Fi de casa", não mais "conhecer o
token". Aceitável pra um assistente pessoal em rede doméstica; se essa
rede for compartilhada com gente não confiável (ex.: apê compartilhado,
rede de trabalho), desligue `modulos.servidor` ou rode só com token
manual (edite este arquivo pra tirar o token da resposta).

Protocolo (só dentro da rede local -- ver server/README.md):
    celular manda UDP broadcast b"JARVIS_DISCOVER" na porta 8766
    PC responde (unicast, só pro IP de quem perguntou) com JSON:
        {"nome": "Ultron", "porta_http": <porta>, "token": <token>}
"""

import json
import socket
import threading

from logs.logger import get_logger

log = get_logger("server")

_MAGIC = b"JARVIS_DISCOVER"
_DISCOVERY_PORT = 8766


def _listen(http_port: int, token: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", _DISCOVERY_PORT))
    except OSError as e:
        log.warning("não consegui abrir a porta de descoberta UDP %s: %s", _DISCOVERY_PORT, e)
        return

    resposta = json.dumps({"nome": "Ultron", "porta_http": http_port, "token": token}).encode("utf-8")
    log.info("descoberta automática do app do celular ativa na porta UDP %s", _DISCOVERY_PORT)

    while True:
        try:
            dados, endereco = sock.recvfrom(1024)
        except OSError:
            break
        if dados.strip() == _MAGIC:
            try:
                sock.sendto(resposta, endereco)
            except OSError:
                pass


def start_discovery(http_port: int, token: str):
    """Sobe o respondedor de descoberta numa thread de fundo (daemon).
    Melhor-esforço: se a porta UDP já estiver em uso por outra coisa,
    só loga um aviso -- o app do celular ainda funciona com IP/token
    digitados manualmente, isso é só uma conveniência a mais."""
    thread = threading.Thread(target=_listen, args=(http_port, token), daemon=True)
    thread.start()
    return thread
