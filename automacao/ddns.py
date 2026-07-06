"""
automacao/ddns.py
====================
Acesso remoto DIRETO (sem túnel/relay de terceiro, ver server/tunnel.py
pra comparação): atualiza um hostname de DNS dinâmico (DuckDNS,
gratuito) com o IP público atual do PC, pra você conseguir usar sempre
o MESMO endereço (`<subdominio>.duckdns.org`) mesmo que seu provedor de
internet troque seu IP público de vez em quando.

Isso NÃO substitui configurar o encaminhamento de porta (port
forwarding) no seu roteador -- essa parte é manual, feita uma vez,
direto no painel do roteador (ver automacao/README.md pro passo a
passo genérico). O DDNS só resolve "que IP é esse hostname agora",
não abre porta nenhuma sozinho.

Por que DuckDNS: gratuito, sem cartão de crédito, e a API de
atualização mais simples que existe (uma requisição HTTP só) -- mas
exige VOCÊ criar a conta gratuita em https://www.duckdns.org e pegar
seu token; não tem como eu fazer isso por você.

IMPORTANTE -- diferente do túnel Cloudflare (que fornece HTTPS): aqui
o tráfego vai DIRETO do celular pro seu roteador, sem TLS por padrão.
O Bearer token do servidor (server/http_server.py) trafega em texto
puro pela internet -- ver aviso de segurança em automacao/README.md.

IMPORTANTE -- por que configurar isso NUNCA acontece via texto de
chat: o token do DuckDNS é uma credencial (mesmo princípio de
automacao/logins_web.py) -- `core/jarvis.py:process()` grava toda
mensagem no histórico ANTES de qualquer plugin rodar, então digitar o
token no chat já o deixaria salvo em texto puro no banco. Por isso
`configurar()` só é chamado pelo CLI (`python -m automacao.ddns`).
"""

import urllib.parse
import urllib.request

from automacao import tasks
from config.settings import get_settings
from logs.logger import get_logger

log = get_logger("automacao")

_INTERVALO_ATUALIZACAO = 900  # 15 minutos
_KEYRING_SERVICE = "jarvis_ddns"

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False


def available() -> bool:
    return HAS_KEYRING


def atualizar(subdominio: str, token: str) -> str:
    """Chama a API do DuckDNS uma vez. Retorna o corpo da resposta
    ("OK" ou "KO")."""
    url = (
        "https://www.duckdns.org/update?domains=" + urllib.parse.quote(subdominio) +
        "&token=" + urllib.parse.quote(token) + "&ip="
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.read().decode("utf-8").strip()


def configurar(subdominio: str, token: str):
    """Salva o subdomínio (não-secreto, config.json) e o token (secreto,
    keyring) -- chamado SÓ pelo CLI deste módulo, nunca pelo chat."""
    if not HAS_KEYRING:
        raise RuntimeError("Instale 'keyring' (requirements-automacao.txt) pra guardar o token com segurança.")
    settings = get_settings()
    settings.set("servidor.ddns_subdominio", subdominio.strip())
    settings.save()
    keyring.set_password(_KEYRING_SERVICE, subdominio.strip(), token.strip())


def subdominio_configurado() -> str:
    return get_settings().get("servidor.ddns_subdominio", "") or ""


def _token_salvo(subdominio: str):
    if not HAS_KEYRING or not subdominio:
        return None
    return keyring.get_password(_KEYRING_SERVICE, subdominio)


def _tick(subdominio: str, token: str):
    try:
        resultado = atualizar(subdominio, token)
        if resultado != "OK":
            log.warning("ddns: DuckDNS respondeu '%s' (esperado 'OK') pra '%s'", resultado, subdominio)
    except Exception as e:
        log.warning("ddns: falha ao atualizar '%s': %s", subdominio, e)


def iniciar(jarvis):
    """Chamado no startup do Ultron -- só agenda a atualização
    periódica se já houver um subdomínio configurado (via
    `python -m automacao.ddns`)."""
    if not jarvis.settings.is_module_enabled("automacao"):
        return
    subdominio = subdominio_configurado()
    if not subdominio:
        return
    token = _token_salvo(subdominio)
    if not token:
        log.warning("ddns: subdomínio '%s' configurado mas sem token no keyring -- rode 'python -m automacao.ddns' de novo", subdominio)
        return
    _tick(subdominio, token)  # atualiza uma vez já no início, não só depois de 15min
    tasks.schedule_recurring("ddns_duckdns", _INTERVALO_ATUALIZACAO, _tick, subdominio, token)


def _cli():
    import getpass
    print("Configurar DuckDNS (grátis) -- crie sua conta antes em https://www.duckdns.org")
    subdominio = input("Subdomínio (ex.: meujarvis -> vira meujarvis.duckdns.org): ").strip()
    token = getpass.getpass("Token do DuckDNS (não aparece na tela): ")
    if not (subdominio and token):
        print("Os dois campos são obrigatórios. Cancelado.")
        return
    try:
        configurar(subdominio, token)
        resultado = atualizar(subdominio, token)
    except Exception as e:
        print(f"Falha ao configurar/testar: {e}")
        return
    if resultado == "OK":
        print(f"Configurado! {subdominio}.duckdns.org agora aponta pro seu IP público atual.")
        print("Falta só encaminhar a porta do Ultron no seu roteador -- veja automacao/README.md.")
    else:
        print(f"DuckDNS respondeu '{resultado}' (esperado 'OK') -- confira o subdomínio/token.")


if __name__ == "__main__":
    _cli()
