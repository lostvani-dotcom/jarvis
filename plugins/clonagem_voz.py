"""
plugins/clonagem_voz.py
==========================
Comandos de chat/voz pra clonar a PRÓPRIA voz do usuário (ver
voz/clonagem.py -- XTTS v2, offline, zero-shot a partir de uma amostra
curta). Só existe comando pra gravar a SUA voz, nunca a de outra
pessoa -- ver a docstring de voz/clonagem.py sobre por que essa
fronteira é deliberada.

Comandos:
    "grava minha voz" / "clona minha voz" -> grava ~20s do microfone
        como amostra de referência (BLOQUEIA enquanto grava -- um aviso
        é disparado antes, ver _abrir_gravacao)
    "fala com a minha voz" / "usa minha voz clonada" -> ativa (pra
        conversa normal, ver voz/tts.py)
    "volta pra voz normal" / "desativa minha voz clonada" -> desativa
    "esquece minha voz clonada" -> apaga a amostra gravada
    "manda um áudio dizendo X" / "gera um áudio com minha voz dizendo X"
        -> sintetiza X num arquivo PERSISTENTE (data/audios_gerados/,
        ver voz/clonagem.py:gerar_arquivo_compartilhavel) e abre a
        pasta -- pra anexar/enviar manualmente em WhatsApp, Telegram,
        e-mail etc. Independente do toggle "voz_clonada_ativa" -- gerar
        um áudio avulso não muda como o Ultron fala na conversa normal.
"""

import re

from config.settings import get_settings
from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_GRAVAR_RE = re.compile(
    r"\b(?:grav[ae]|clon[ae]|aprend[ae])\w*\s+(?:a\s+)?minha\s+voz\b", re.IGNORECASE,
)
_ATIVAR_RE = re.compile(
    r"\bfala\s+com\s+a\s+minha\s+voz\b|\b(?:usa|use|ativ[ae])\w*\s+minha\s+voz\s+clonada\b", re.IGNORECASE,
)
_DESATIVAR_RE = re.compile(
    r"\bvolta\s+pra\s+voz\s+normal\b|\b(?:desativ[ae]|deslig[ae])\w*\s+minha\s+voz\s+clonada\b", re.IGNORECASE,
)
_ESQUECER_RE = re.compile(r"\besque[çc]\w*\s+minha\s+voz\s+clonada\b", re.IGNORECASE)
_GERAR_AUDIO_RE = re.compile(
    r"\b(?:manda|mande|gera|gere|cria|crie|faz|fa[çc]a)\w*\s+um\s+[áa]udio\s+(?:dizendo|falando|com)\s+(.+)",
    re.IGNORECASE,
)


class ClonagemVozPlugin(BasePlugin):
    name = "clonagem_voz"
    description = "Grava, ativa, desativa e apaga a clonagem da própria voz do usuário (XTTS)"
    triggers = ["minha voz", "voz clonada"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _GRAVAR_RE.search(t) or _ATIVAR_RE.search(t) or _DESATIVAR_RE.search(t)
            or _ESQUECER_RE.search(t) or _GERAR_AUDIO_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()
        if _GRAVAR_RE.search(t):
            return self._gravar()
        if _DESATIVAR_RE.search(t):
            return self._desativar()
        if _ATIVAR_RE.search(t):
            return self._ativar()
        if _ESQUECER_RE.search(t):
            return self._esquecer()
        m = _GERAR_AUDIO_RE.search(t)
        if m:
            return self._gerar_audio(m.group(1))
        return None

    def _gravar(self):
        from voz import clonagem
        if not clonagem.disponivel():
            return Answer(
                "Clonagem de voz indisponível -- instale com "
                "'pip install \"coqui-tts[cpu]\"' (pacote pesado, ~1.8GB de modelo baixado na "
                "primeira vez).",
                Confidence.GUESS,
            )

        duracao = clonagem.DURACAO_AMOSTRA_PADRAO
        # Aviso ANTES de começar a bloquear -- sem isso, quem pediu não
        # saberia que precisa começar a falar agora (o comando de chat
        # só devolve uma resposta DEPOIS que a gravação inteira termina,
        # não dá pra avisar "já pode falar" no meio do caminho).
        from automacao.notify import notify
        notify("Ultron", f"Gravando sua voz por {int(duracao)}s -- comece a falar naturalmente agora.")

        device_index = get_settings().get("voz.microfone_index", None)
        resultado = clonagem.gravar_amostra(duracao, device_index=device_index)
        if not resultado["sucesso"]:
            return Answer(f"Não consegui gravar sua voz: {resultado['motivo']}.", Confidence.GUESS)
        return Answer(
            'Gravei sua voz. Diga "fala com a minha voz" pra eu começar a responder com ela, ou '
            'continue com a voz de sempre se preferir. Detalhe importante: a primeira vez que eu '
            "falar vai baixar o modelo (~1.8GB) e demorar mais -- e o uso desse modelo segue a "
            "licença gratuita da Coqui pra uso pessoal (CPML, coqui.ai/cpml).",
            Confidence.CONFIRMED,
        )

    def _ativar(self):
        from voz import clonagem
        if not clonagem.tem_amostra():
            return Answer(
                'Ainda não gravei sua voz -- diga "grava minha voz" primeiro (leva uns 20 segundos).',
                Confidence.GUESS,
            )
        if not clonagem.disponivel():
            return Answer(
                "Clonagem de voz indisponível -- instale com 'pip install \"coqui-tts[cpu]\"'.",
                Confidence.GUESS,
            )
        settings = get_settings()
        settings.set("personalidade.voz_clonada_ativa", True)
        settings.save()
        return Answer(
            "Combinado -- a partir de agora falo com a sua voz (a primeira fala demora um "
            "pouco mais, o modelo carrega na hora).",
            Confidence.CONFIRMED,
        )

    def _desativar(self):
        settings = get_settings()
        settings.set("personalidade.voz_clonada_ativa", False)
        settings.save()
        return Answer("Voz clonada desligada -- volto a falar com a voz normal/robótica.", Confidence.CONFIRMED)

    def _esquecer(self):
        from voz import clonagem
        settings = get_settings()
        settings.set("personalidade.voz_clonada_ativa", False)
        settings.save()
        if clonagem.esquecer_amostra():
            return Answer("Esqueci sua voz clonada -- a amostra gravada foi apagada.", Confidence.CONFIRMED)
        return Answer("Eu não tinha nenhuma amostra da sua voz gravada.", Confidence.CONFIRMED)

    def _gerar_audio(self, texto: str):
        from voz import clonagem
        texto = texto.strip(" ?.!\"'")
        if not texto:
            return Answer("Dizendo o quê no áudio?", Confidence.GUESS)
        if not clonagem.tem_amostra():
            return Answer(
                'Ainda não gravei sua voz -- diga "grava minha voz" primeiro (leva uns 20 segundos).',
                Confidence.GUESS,
            )
        if not clonagem.disponivel():
            return Answer(
                "Clonagem de voz indisponível -- instale com 'pip install \"coqui-tts[cpu]\"'.",
                Confidence.GUESS,
            )
        try:
            caminho = clonagem.get_cloner().gerar_arquivo_compartilhavel(texto)
        except Exception as e:
            return Answer(f"Não consegui gerar o áudio: {e}", Confidence.GUESS)
        self._abrir_pasta(caminho)
        return Answer(
            f'Pronto -- gravei um áudio com a sua voz dizendo "{texto}" em:\n{caminho}\n'
            "Abri a pasta pra você já poder anexar/enviar em qualquer app (WhatsApp, Telegram, "
            "e-mail...).",
            Confidence.CONFIRMED,
        )

    def _abrir_pasta(self, caminho: str):
        import os
        import sys
        try:
            pasta = os.path.dirname(caminho)
            if sys.platform == "win32":
                os.startfile(pasta)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", pasta])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", pasta])
        except Exception:
            pass  # melhor-esforço -- o caminho já foi informado na resposta de qualquer forma
