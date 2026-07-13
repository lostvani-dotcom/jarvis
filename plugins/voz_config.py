"""
plugins/voz_config.py
========================
Comandos de chat/voz pra configurar o próprio jeito do Ultron ouvir e
responder por voz -- antes desses comandos, `voz.ativar_wakeword`,
`voz.conversa_continua_segundos`, `voz.palavra_chave` e
`personalidade.voz_robotica` só eram ajustáveis editando config.json à
mão. Tudo aqui só mexe em configuração (settings.set + save) -- quem
lê de verdade essas chaves é voz/loop.py, voz/wakeword.py e voz/tts.py,
na PRÓXIMA vez que o modo voz for iniciado (não muda uma sessão de voz
já rodando, só a próxima).

Comandos:
    "liga a conversa contínua" / "desliga a conversa contínua"
    "liga a palavra de ativação" / "desliga a palavra de ativação"
    "muda a palavra de ativação para <palavra>"
    "liga a voz robótica" / "desliga a voz robótica"
"""

import re

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_CONVERSA_LIGA_RE = re.compile(r"\blig[ae]\w*\s+.*\bconversa\s+cont[ií]nua\b", re.IGNORECASE)
_CONVERSA_DESLIGA_RE = re.compile(r"\b(deslig[ae]|desativ[ae])\w*\s+.*\bconversa\s+cont[ií]nua\b", re.IGNORECASE)

_WAKEWORD_LIGA_RE = re.compile(
    r"\blig[ae]\w*\s+.*\bpalavra\s+de\s+ativa[çc][ãa]o\b|\bativ[ae]\w*\s+.*\bpalavra\s+de\s+ativa[çc][ãa]o\b",
    re.IGNORECASE,
)
_WAKEWORD_DESLIGA_RE = re.compile(
    r"\b(deslig[ae]|desativ[ae])\w*\s+.*\bpalavra\s+de\s+ativa[çc][ãa]o\b",
    re.IGNORECASE,
)
_WAKEWORD_MUDAR_RE = re.compile(
    r"\b(?:muda|mude|troca|troque)\w*\s+(?:a\s+)?palavra\s+de\s+ativa[çc][ãa]o\s+para\s+(\w+)|"
    r"\bminha\s+palavra\s+de\s+ativa[çc][ãa]o\s+agora\s+[ée]\s+(\w+)",
    re.IGNORECASE,
)

_ROBOTICA_LIGA_RE = re.compile(r"\blig[ae]\w*\s+.*\bvoz\s+rob[óo]tica\b|\bativ[ae]\w*\s+.*\bvoz\s+rob[óo]tica\b", re.IGNORECASE)
_ROBOTICA_DESLIGA_RE = re.compile(r"\b(deslig[ae]|desativ[ae])\w*\s+.*\bvoz\s+rob[óo]tica\b", re.IGNORECASE)


class VozConfigPlugin(BasePlugin):
    name = "voz_config"
    description = "Liga/desliga conversa contínua, palavra de ativação e voz robótica; muda a palavra de ativação"
    triggers = ["conversa contínua", "palavra de ativação", "voz robótica"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _CONVERSA_LIGA_RE.search(t) or _CONVERSA_DESLIGA_RE.search(t)
            or _WAKEWORD_LIGA_RE.search(t) or _WAKEWORD_DESLIGA_RE.search(t) or _WAKEWORD_MUDAR_RE.search(t)
            or _ROBOTICA_LIGA_RE.search(t) or _ROBOTICA_DESLIGA_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        settings = get_settings()

        if _CONVERSA_DESLIGA_RE.search(t):
            settings.set("voz.conversa_continua_segundos", 0)
            settings.save()
            return Answer(
                "Conversa contínua desligada -- a partir da próxima vez que eu iniciar o modo voz, "
                "vou exigir a palavra de ativação em toda frase de novo.",
                Confidence.CONFIRMED,
            )
        if _CONVERSA_LIGA_RE.search(t):
            settings.set("voz.conversa_continua_segundos", 18.0)
            settings.save()
            return Answer(
                "Conversa contínua ligada -- depois que eu responder, você tem 18s pra continuar "
                'falando sem precisar repetir a palavra de ativação (vale a partir da próxima vez '
                "que eu iniciar o modo voz).",
                Confidence.CONFIRMED,
            )

        if _WAKEWORD_DESLIGA_RE.search(t):
            settings.set("voz.ativar_wakeword", False)
            settings.save()
            return Answer(
                "Palavra de ativação desligada -- a partir da próxima vez que eu iniciar o modo voz, "
                "vou ouvir direto, sem precisar chamar meu nome antes.",
                Confidence.CONFIRMED,
            )
        if _WAKEWORD_LIGA_RE.search(t):
            settings.set("voz.ativar_wakeword", True)
            settings.save()
            palavra = settings.get("voz.palavra_chave", "ultron")
            return Answer(
                f'Palavra de ativação ligada -- a partir da próxima vez que eu iniciar o modo voz, '
                f'vou esperar você dizer "{palavra}" antes de cada comando.',
                Confidence.CONFIRMED,
            )

        m = _WAKEWORD_MUDAR_RE.search(t)
        if m:
            palavra = (m.group(1) or m.group(2) or "").strip().lower()
            if not palavra:
                return Answer("Mudar a palavra de ativação para qual palavra?", Confidence.GUESS)
            settings.set("voz.palavra_chave", palavra)
            settings.save()
            return Answer(
                f'Combinado, minha palavra de ativação agora é "{palavra}" (vale a partir da '
                "próxima vez que eu iniciar o modo voz).",
                Confidence.CONFIRMED,
            )

        if _ROBOTICA_DESLIGA_RE.search(t):
            settings.set("personalidade.voz_robotica", False)
            settings.save()
            return Answer(
                "Voz robótica desligada -- a partir da próxima vez que eu iniciar o modo voz, "
                "falo com a voz normal.",
                Confidence.CONFIRMED,
            )
        if _ROBOTICA_LIGA_RE.search(t):
            settings.set("personalidade.voz_robotica", True)
            settings.save()
            return Answer(
                "Voz robótica ligada -- a partir da próxima vez que eu iniciar o modo voz, falo "
                "mais grave e mecânico.",
                Confidence.CONFIRMED,
            )

        return None
