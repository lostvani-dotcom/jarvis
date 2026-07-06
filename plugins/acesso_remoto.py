"""
plugins/acesso_remoto.py
===========================
Duas formas de acessar o Ultron de fora da rede local:

1. **Túnel Cloudflare** (server/tunnel.py) -- "ativa o acesso remoto".
   Zero configuração de roteador, HTTPS de graça, mas depende de um
   serviço terceiro (Cloudflare) e a URL muda a cada reinício.
2. **Endereço direto com DNS dinâmico** (automacao/ddns.py) -- "qual o
   endereço remoto direto". Não depende de nenhum serviço de túnel/
   relay -- o celular conecta DIRETO no seu roteador. Em troca, exige
   você configurar o encaminhamento de porta no roteador (manual, uma
   vez só) e o tráfego vai SEM HTTPS por padrão (o Bearer token do
   servidor trafega em texto puro pela internet -- ver aviso em
   automacao/README.md). Configurar o DuckDNS é feito pelo CLI
   (`python -m automacao.ddns`), nunca pelo chat (mesmo motivo de
   automacao/logins_web.py: o token é uma credencial).

Em ambos os casos, o Bearer token (server/http_server.py) continua
sendo a autenticação de verdade.

Comandos:
    "ativa o acesso remoto" / "quero acessar de longe" -> sobe o
    túnel Cloudflare, mostra a URL (e o token) pra colar no app
    "desativa o acesso remoto" -> derruba o túnel
    "qual a url remota" / "status do acesso remoto"
    "qual o endereço remoto direto" -> mostra o endereço DDNS (se
    configurado via `python -m automacao.ddns`) pra colar no app
"""

import re

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin
from server import tunnel
from server.http_server import get_or_create_token

_ENABLE_RE = re.compile(
    r"\bativ[ae]\w*\s+.*\bacesso\s+remoto\b|\bquero\s+acessar\s+de\s+longe\b|"
    r"\blig[ae]\w*\s+.*\bt[uú]nel\b",
    re.IGNORECASE,
)
_DISABLE_RE = re.compile(r"\bdesativ[ae]\w*\s+.*\bacesso\s+remoto\b|\bdeslig[ae]\w*\s+.*\bt[uú]nel\b", re.IGNORECASE)
_STATUS_RE = re.compile(r"\burl\s+remota\b|\bstatus\s+d[oa]\s+acesso\s+remoto\b", re.IGNORECASE)
_DIRETO_RE = re.compile(r"\bendere[çc]o\s+remoto\s+direto\b|\bacesso\s+remoto\s+direto\b", re.IGNORECASE)
_DDNS_CHAT_RE = re.compile(r"\bconfigur[ae]\w*\s+.*\bduckdns\b|\bduckdns\b.*\btoken\b", re.IGNORECASE)


class AcessoRemotoPlugin(BasePlugin):
    name = "acesso_remoto"
    description = "Liga/desliga acesso remoto ao Ultron de fora da rede local (túnel Cloudflare ou DDNS direto)"
    triggers = ["acesso remoto", "acessar de longe", "túnel", "tunel", "url remota", "endereço remoto direto"]

    def matches(self, text: str) -> bool:
        return bool(
            _ENABLE_RE.search(text) or _DISABLE_RE.search(text) or _STATUS_RE.search(text)
            or _DIRETO_RE.search(text) or _DDNS_CHAT_RE.search(text)
        )

    def handle(self, text: str, context: dict):
        if _DDNS_CHAT_RE.search(text):
            return Answer(
                "Por segurança, não configuro o token do DuckDNS pelo chat -- ficaria salvo em "
                "texto puro no histórico de conversa. Rode 'python -m automacao.ddns' no terminal "
                "(a senha/token não aparece na tela). Depois, é só dizer 'qual o endereço remoto "
                "direto' aqui.",
                Confidence.GUESS,
            )
        if _DIRETO_RE.search(text):
            return self._endereco_direto()
        if _DISABLE_RE.search(text):
            return self._desativar()
        if _STATUS_RE.search(text):
            return self._status()
        if _ENABLE_RE.search(text):
            return self._ativar()
        return None

    def _endereco_direto(self):
        from automacao import ddns

        subdominio = ddns.subdominio_configurado()
        if not subdominio:
            return Answer(
                "Ainda não configurei o acesso remoto direto. Rode 'python -m automacao.ddns' no "
                "terminal (crie uma conta grátis em duckdns.org antes) -- isso não passa pelo chat "
                "porque envolve um token. Depois disso, também é preciso encaminhar a porta do "
                "Ultron no seu roteador (veja automacao/README.md) -- essa parte eu não consigo "
                "fazer por você.",
                Confidence.GUESS,
            )
        porta = get_settings().get("servidor.porta", 8765)
        token = get_or_create_token()
        return Answer(
            f'No app do celular, cole isto no campo "IP do PC ou URL remota": '
            f'http://{subdominio}.duckdns.org:{porta}\nE no campo Token: {token}\n\n'
            "Isso só funciona de fora de casa se você já configurou o encaminhamento de porta "
            "no roteador. Atenção: sem túnel, o tráfego não tem HTTPS -- evite usar em Wi-Fi "
            "pública não confiável.",
            Confidence.CONFIRMED,
        )

    def _ativar(self):
        if not tunnel.disponivel():
            try:
                tunnel.baixar_cloudflared()
            except Exception as e:
                return Answer(f"Não consegui baixar o cloudflared: {e}", Confidence.GUESS)
        porta = int(get_settings().get("servidor.porta", 8765))
        try:
            url = tunnel.iniciar_tunel(porta)
        except Exception as e:
            return Answer(f"Não consegui iniciar o túnel: {e}", Confidence.GUESS)
        token = get_or_create_token()
        return Answer(
            "Acesso remoto LIGADO. No app do celular (fora da sua Wi-Fi de casa), cole isso "
            f'no campo "IP do PC ou URL remota": {url}\nE no campo Token: {token}\n\n'
            "Atenção: essa URL muda toda vez que o Ultron reinicia -- se reiniciar, peça "
            '"qual a url remota" de novo. Diga "desativa o acesso remoto" quando não precisar mais.',
            Confidence.CONFIRMED,
        )

    def _desativar(self):
        if not tunnel.tunel_ativo():
            return Answer("O acesso remoto já estava desligado.", Confidence.CONFIRMED)
        tunnel.parar_tunel()
        return Answer("Acesso remoto desligado. O Ultron só responde na rede local agora.", Confidence.CONFIRMED)

    def _status(self):
        if tunnel.tunel_ativo() and tunnel.url_atual():
            return Answer(f"Acesso remoto ligado: {tunnel.url_atual()}", Confidence.CONFIRMED)
        return Answer(
            'Acesso remoto está desligado. Diga "ativa o acesso remoto" pra ligar.', Confidence.CONFIRMED
        )
