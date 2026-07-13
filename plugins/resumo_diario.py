"""
plugins/resumo_diario.py
===========================
"Resumo do dia": saudação de acordo com a hora + lembretes de hoje +
quantas notificações recentes chegaram, tudo num único comando. Não
inventa dado nenhum que o Ultron não tem de verdade -- sem integração
de previsão do tempo (precisaria de uma chave de API externa), o
resumo diz isso explicitamente em vez de inventar um "vai chover hoje"
sem fonte nenhuma.

Pra rodar sozinho todo dia (ex.: às 7h), combine com o sistema de
macros já existente (ver plugins/macros.py):
    "cria uma macro bom dia: resumo do dia"
    "agenda a macro bom dia todo dia às 7h"

Comandos:
    "resumo do dia" / "me dá um resumo do dia" / "como está o dia hoje"
"""

import re
from datetime import datetime

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TRIGGER_RE = re.compile(
    r"\bresumo\s+do\s+dia\b|"
    r"\bcomo\s+est[aá]\s+o\s+dia\b|"
    r"\bo\s+que\s+tem\s+pra\s+hoje\b",
    re.IGNORECASE,
)


def _saudacao(hora: int) -> str:
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


# strftime("%A") depende do locale do SO (em inglês por padrão no
# Windows, sem pt_BR instalado) -- mapeamento manual evita "Monday" em
# vez de "segunda-feira" numa frase toda em português.
_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _data_por_extenso(agora: datetime) -> str:
    return f"{_DIAS_SEMANA[agora.weekday()]}, {agora.strftime('%d/%m')}"


class ResumoDiarioPlugin(BasePlugin):
    name = "resumo_diario"
    description = "Resumo do dia: saudação, lembretes de hoje e notificações recentes"
    triggers = ["resumo do dia", "como está o dia hoje", "o que tem pra hoje"]

    def matches(self, text: str) -> bool:
        return bool(_TRIGGER_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        agora = datetime.now()
        user_id = context.get("user_id", "default_user")
        partes = [f"{_saudacao(agora.hour)}! Hoje é {_data_por_extenso(agora)}."]

        partes.append(self._lembretes_de_hoje(user_id, agora))
        partes.append(self._notificacoes_recentes())

        partes.append(
            'Não tenho integração de previsão do tempo configurada (precisaria de uma chave de '
            "API externa) -- se quiser, posso te ajudar a configurar isso no futuro."
        )

        return Answer("\n".join(p for p in partes if p), Confidence.CONFIRMED)

    def _lembretes_de_hoje(self, user_id: str, agora: datetime) -> str:
        try:
            from automacao import reminders
            pendentes = reminders.list_pending(user_id)
        except Exception:
            return ""
        hoje = agora.strftime("%Y-%m-%d")
        de_hoje = [r for r in pendentes if str(r.get("quando", "")).startswith(hoje)]
        if not de_hoje:
            return "Nenhum lembrete pendente pra hoje."
        linhas = []
        for r in de_hoje:
            try:
                hora = datetime.fromisoformat(r["quando"]).strftime("%H:%M")
            except (KeyError, ValueError, TypeError):
                hora = "?"
            linhas.append(f"- {hora}: {r['mensagem']}")
        return f"Lembretes de hoje ({len(de_hoje)}):\n" + "\n".join(linhas)

    def _notificacoes_recentes(self) -> str:
        try:
            from automacao import notification_inbox
            total = len(notification_inbox.todas())
        except Exception:
            return ""
        if total == 0:
            return "Nenhuma notificação recente do celular."
        return f"{total} notificação(ões) recente(s) do celular (diga \"o que eu perdi\" pra ver o detalhe)."
