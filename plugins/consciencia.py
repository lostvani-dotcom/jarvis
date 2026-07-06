"""
plugins/consciencia.py
=========================
Lado de chat da "consciência interna" (core/autoconsciencia.py): o
Ultron responde tecnicamente sobre o próprio estado -- memória do
processo, tempo no ar, plugins carregados, módulos disponíveis,
provedores de IA prontos, rotinas de fundo ativas ("agentes") e
avisos/erros registrados no log hoje.

Diferente do "como você está?" casual (core/conversation.py, que dá uma
resposta de conversa): aqui é um diagnóstico técnico com números reais.

Comandos:
    "diagnóstico" / "status técnico" / "relatório interno"
    "como você está por dentro" / "como você está tecnicamente"
    "quais são suas capacidades" / "quais são seus limites"
"""

import re

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_RE = re.compile(
    r"\bdiagn[óo]stico\b|\bstatus\s+t[ée]cnico\b|\brelat[óo]rio\s+interno\b|"
    r"\bcomo\s+voc[êe]\s+est[áa]\s+(?:por\s+dentro|tecnicamente)\b|"
    r"\bseu\s+estado\s+(?:interno|t[ée]cnico)\b|"
    r"\b(?:suas\s+capacidades|seus\s+limites|seus\s+m[óo]dulos)\b|"
    r"\bcomo\s+voc[êe]\s+se\s+sente\s+tecnicamente\b",
    re.IGNORECASE,
)


class ConscienciaPlugin(BasePlugin):
    name = "consciencia"
    description = "Diagnóstico técnico do próprio Ultron: memória, uptime, plugins, módulos, IA, rotinas ativas, erros do dia"
    triggers = [
        "diagnóstico", "diagnostico", "status técnico", "status tecnico",
        "relatório interno", "relatorio interno", "como você está por dentro",
        "como voce esta por dentro", "suas capacidades", "seus limites",
    ]

    def matches(self, text: str) -> bool:
        return bool(_RE.search(text.strip()))

    def handle(self, text: str, context: dict):
        jarvis = context.get("jarvis")
        if jarvis is None:
            return Answer("Não consegui acessar meu próprio núcleo pra fazer o diagnóstico agora.", Confidence.GUESS)
        from core import autoconsciencia
        try:
            corpo = autoconsciencia.descrever(jarvis)
        except Exception as e:
            return Answer(f"Falhei ao montar o diagnóstico: {e}", Confidence.GUESS)
        return Answer("Meu estado técnico agora:\n" + corpo, Confidence.CONFIRMED)
