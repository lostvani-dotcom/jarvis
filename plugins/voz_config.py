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
    "que microfones você tem" / "lista microfones"
    "usa o microfone <número>" / "muda pro microfone <número>"
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

_MIC_LISTAR_RE = re.compile(r"\bque\s+microfones?\s+voc[eê]\s+tem\b|\blist[ae]\w*\s+(?:os\s+)?microfones?\b", re.IGNORECASE)
# O conector opcional cobria "pro microfone"/"para o microfone" (formas
# contraídas ou completas de "para o") mas não o artigo solto "o" --
# faltava exatamente a forma do exemplo documentado ("usa o microfone
# <número>"), que ficava sem nenhuma resposta.
_MIC_USAR_RE = re.compile(r"\b(?:usa|use|muda|mude)\w*\s+(?:pro?\s+|para\s+o\s+|o\s+)?microfone\s+(\d+)\b", re.IGNORECASE)


class VozConfigPlugin(BasePlugin):
    name = "voz_config"
    description = "Liga/desliga conversa contínua, palavra de ativação, voz robótica e microfone usado"
    triggers = ["conversa contínua", "palavra de ativação", "voz robótica", "microfone"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _CONVERSA_LIGA_RE.search(t) or _CONVERSA_DESLIGA_RE.search(t)
            or _WAKEWORD_LIGA_RE.search(t) or _WAKEWORD_DESLIGA_RE.search(t) or _WAKEWORD_MUDAR_RE.search(t)
            or _ROBOTICA_LIGA_RE.search(t) or _ROBOTICA_DESLIGA_RE.search(t)
            or _MIC_LISTAR_RE.search(t) or _MIC_USAR_RE.search(t)
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

        if _MIC_LISTAR_RE.search(t):
            return self._listar_microfones()
        m = _MIC_USAR_RE.search(t)
        if m:
            return self._usar_microfone(int(m.group(1)))

        return None

    def _listar_microfones(self):
        from voz.stt import listar_microfones
        microfones = listar_microfones()
        if not microfones:
            return Answer(
                "Não encontrei nenhum microfone -- confira se tem um conectado/habilitado no Windows.",
                Confidence.GUESS,
            )
        linhas = [
            f"- {m['index']}: {m['nome']}" + (" (padrão do sistema)" if m["padrao"] else "")
            for m in microfones
        ]
        return Answer(
            "Microfones disponíveis:\n" + "\n".join(linhas) +
            '\n\nDiga "usa o microfone <número>" pra escolher um.',
            Confidence.CONFIRMED,
        )

    def _usar_microfone(self, indice: int):
        from voz.stt import listar_microfones
        validos = {m["index"] for m in listar_microfones()}
        if indice not in validos:
            return Answer(
                f'Não achei o microfone {indice} -- diga "que microfones você tem" pra ver os índices válidos.',
                Confidence.GUESS,
            )
        settings = get_settings()
        settings.set("voz.microfone_index", indice)
        settings.save()
        return Answer(
            f"Combinado, vou usar o microfone {indice} a partir da próxima vez que eu iniciar o modo voz.",
            Confidence.CONFIRMED,
        )
