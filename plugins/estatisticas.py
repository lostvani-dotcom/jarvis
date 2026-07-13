"""
plugins/estatisticas.py
==========================
Lado de chat de automacao/estatisticas.py -- "quanto eu uso o Ultron"
num período, e o que mais uso. Mesmos dados também disponíveis pelo
Companion via GET /estatisticas (server/http_server.py), numa telinha
dedicada nas configurações.

Comandos:
    "estatísticas de uso" / "quanto eu uso o ultron" / "minhas estatísticas"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_TRIGGER_RE = re.compile(
    r"\bestat[ií]sticas?\s+de\s+uso\b|"
    r"\bquanto\s+eu\s+uso\s+o\s+ultron\b|"
    r"\bminhas?\s+estat[ií]sticas\b",
    re.IGNORECASE,
)


class EstatisticasPlugin(BasePlugin):
    name = "estatisticas"
    description = "Estatísticas de uso: quantas mensagens processadas e o que mais foi usado"
    triggers = ["estatísticas de uso", "quanto eu uso o ultron", "minhas estatísticas"]

    def matches(self, text: str) -> bool:
        return bool(_TRIGGER_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        from automacao import estatisticas
        return Answer(estatisticas.formatar_texto(dias=7), Confidence.CONFIRMED)
