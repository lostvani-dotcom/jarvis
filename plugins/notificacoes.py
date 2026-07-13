"""
plugins/notificacoes.py
==========================
Resumo das notificações do celular capturadas pelo Companion (ver
automacao/notification_inbox.py, alimentada via POST /notify --
NotifyListenerService.kt no app). Puramente um RESUMO pra consulta ("o
que eu perdi") -- não interfere em nada no encaminhamento individual
que já existe pra plugins/instagram.py responder sozinho, é só mais
uma leitura da mesma caixa de entrada em memória.

Comandos:
    "resumo das notificações" / "o que eu perdi" / "minhas notificações"
"""

import re
import time

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TRIGGER_RE = re.compile(
    r"\bresumo\s+d[ae]s?\s+notifica[çc][õo]es\b|"
    r"\bo\s+que\s+eu\s+perdi\b|"
    r"\bminhas\s+notifica[çc][õo]es\b|"
    r"\bnotifica[çc][õo]es\s+recentes\b",
    re.IGNORECASE,
)

_NOMES_AMIGAVEIS = {
    "com.instagram.android": "Instagram",
    "com.whatsapp": "WhatsApp",
    "com.facebook.orca": "Messenger",
    "org.telegram.messenger": "Telegram",
    "org.thoughtcrime.securesms": "Signal",
    "com.discord": "Discord",
    "com.google.android.apps.messaging": "Mensagens (SMS)",
}


class NotificacoesPlugin(BasePlugin):
    name = "notificacoes"
    description = "Resume as notificações recentes do celular capturadas pelo Companion"
    triggers = ["resumo das notificações", "o que eu perdi", "minhas notificações"]

    def matches(self, text: str) -> bool:
        return bool(_TRIGGER_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        from automacao import notification_inbox

        itens = notification_inbox.todas()
        if not itens:
            return Answer(
                "Nenhuma notificação capturada ainda -- confira se o Companion está instalado "
                "e com o acesso a notificações liberado.",
                Confidence.CONFIRMED,
            )

        agora = time.time()
        por_app = {}
        for item in itens:
            pacote = item.get("pacote", "")
            grupo = por_app.setdefault(pacote, {"qtd": 0, "ultima": 0.0})
            grupo["qtd"] += 1
            grupo["ultima"] = max(grupo["ultima"], item.get("quando", 0.0))

        linhas = []
        for pacote, info in sorted(por_app.items(), key=lambda kv: kv[1]["ultima"], reverse=True):
            nome = _NOMES_AMIGAVEIS.get(pacote, pacote)
            minutos_atras = max(0, int((agora - info["ultima"]) / 60))
            quando_texto = "agora" if minutos_atras == 0 else f"há {minutos_atras} min"
            mensagem_texto = "mensagem" if info["qtd"] == 1 else "mensagens"
            linhas.append(f"- {nome}: {info['qtd']} {mensagem_texto} (última {quando_texto})")

        total = len(itens)
        return Answer(
            f"Você tem {total} notificação(ões) recente(s):\n" + "\n".join(linhas),
            Confidence.CONFIRMED,
        )
