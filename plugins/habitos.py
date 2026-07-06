"""
plugins/habitos.py
=====================
"Analisa hábitos no computador e no celular" -- ver automacao/habitos.py
(amostragem periódica de app/janela em primeiro plano, acumulada em
data/jarvis.db). Diferente da timeline (eventos pontuais): isto é uma
CONTAGEM agregada de uso ao longo de dias.

Comandos:
    "quais são meus hábitos no pc" / "analisa meus hábitos no computador"
    "quais são meus hábitos no celular" / "analisa meus hábitos no celular"
"""

import re

from automacao import habitos
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_HABITOS_RE = re.compile(r"\bh[aá]bitos?\b", re.IGNORECASE)
_CELULAR_RE = re.compile(r"\bcelular\b", re.IGNORECASE)
_PC_RE = re.compile(r"\bpc\b|\bcomputador\b", re.IGNORECASE)


class HabitosPlugin(BasePlugin):
    name = "habitos"
    description = "Analisa hábitos de uso (apps mais usados) no PC e no celular"
    triggers = ["hábitos", "habitos"]

    def matches(self, text: str) -> bool:
        return bool(_HABITOS_RE.search(text))

    def handle(self, text: str, context: dict):
        t = text.lower()
        if _CELULAR_RE.search(t) and not _PC_RE.search(t):
            return Answer(habitos.resumo("celular"), Confidence.CONFIRMED)
        if _PC_RE.search(t) and not _CELULAR_RE.search(t):
            return Answer(habitos.resumo("pc"), Confidence.CONFIRMED)
        # Sem especificar -- mostra os dois.
        return Answer(
            f"{habitos.resumo('pc')}\n\n{habitos.resumo('celular')}", Confidence.CONFIRMED
        )
