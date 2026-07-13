"""
plugins/reconhecimento_facial.py
===================================
Comandos de chat para reconhecimento facial de verdade (identificar
QUEM é o rosto, não só que há um rosto) -- via visao/faces.py
(FaceRecognizerLBPH, cv2.face). Antes deste plugin, visao/faces.py só
existia como módulo de baixo nível, sem nenhum comando de chat pra
usar -- reconhecimento facial estava no código mas inacessível.

Comandos:
    "lembra esse rosto como <nome>" / "cadastra o rosto de <nome>" /
    "aprende meu rosto como <nome>" -> abre a câmera, tira várias fotos
        em sequência e cadastra <nome>
    "quem é essa pessoa" / "quem está na câmera" / "reconhece esse
        rosto" -> tira uma foto e diz quem reconhece
    "esquece o rosto de <nome>" / "apaga o rosto de <nome>" -> remove
        o cadastro de <nome>
    "que rostos você conhece" / "rostos cadastrados" -> lista quem já
        foi cadastrado
"""

import re
import time

from core.confidence import Answer, Confidence
from core.plugin_manager import BasePlugin

_LEMBRAR_RE = re.compile(
    r"\b(lembr[ae]|cadastr[ae]|aprend[ae])\w*\s+(?:esse\s+|este\s+|o\s+|meu\s+)?rosto\s+(?:como|de)\s+(.+)",
    re.IGNORECASE,
)
_QUEM_RE = re.compile(
    r"\bquem\s+(?:é|e)\s+(?:essa|esta)\s+pessoa\b|"
    r"\bquem\s+(?:está|esta|ta)\s+n[ao]\s+c[aâ]mera\b|"
    r"\breconhe[çc]e\s+(?:esse|este)\s+rosto\b|"
    r"\bque\s+rosto\s+[ée]\s+esse\b",
    re.IGNORECASE,
)
_ESQUECER_RE = re.compile(r"\b(esque[çc]|apag[ae])\w*\s+o\s+rosto\s+d[eo]\s+(.+)", re.IGNORECASE)
_LISTAR_RE = re.compile(r"\bque\s+rostos\s+voc[eê]\s+conhece\b|\brostos\s+cadastrados\b", re.IGNORECASE)

_NUM_AMOSTRAS = 12  # fotos tiradas em burst durante o cadastro
_INTERVALO_AMOSTRA_SEG = 0.25
_MIN_AMOSTRAS_RECOMENDADO = 5  # abaixo disso, avisa que o modelo pode ficar raso


class ReconhecimentoFacialPlugin(BasePlugin):
    name = "reconhecimento_facial"
    description = "Cadastra e identifica rostos conhecidos pela câmera (reconhecimento facial via OpenCV/LBPH)"
    triggers = ["lembra esse rosto", "quem é essa pessoa", "reconhece esse rosto", "rostos cadastrados"]

    def matches(self, text: str) -> bool:
        t = text.strip()
        return bool(
            _LEMBRAR_RE.search(t) or _QUEM_RE.search(t) or _ESQUECER_RE.search(t) or _LISTAR_RE.search(t)
        )

    def handle(self, text: str, context: dict):
        t = text.strip()

        m = _LEMBRAR_RE.search(t)
        if m:
            return self._cadastrar(m.group(2).strip(" ?.!"))

        m = _ESQUECER_RE.search(t)
        if m:
            return self._esquecer(m.group(2).strip(" ?.!"))

        if _LISTAR_RE.search(t):
            return self._listar()

        if _QUEM_RE.search(t):
            return self._identificar()

        return None

    def _preparar(self):
        """Checa câmera + LBPH disponíveis antes de qualquer captura --
        retorna (camera, recognizer, None) se tudo ok, ou (None, None,
        Answer-de-erro) caso contrário."""
        from visao.camera import Camera
        from visao.faces import get_recognizer

        recognizer = get_recognizer()
        if not recognizer.available():
            return None, None, Answer(
                "Reconhecimento facial indisponível -- instale 'opencv-contrib-python' "
                "(pip install opencv-contrib-python).",
                Confidence.GUESS,
            )
        camera = Camera()
        if not camera.available():
            return None, None, Answer(
                "Não consigo acessar a câmera -- instale 'opencv-python' (requirements-visao.txt).",
                Confidence.GUESS,
            )
        return camera, recognizer, None

    def _cadastrar(self, nome: str):
        if not nome:
            return Answer("Cadastrar o rosto de quem?", Confidence.GUESS)

        camera, recognizer, erro = self._preparar()
        if erro:
            return erro

        try:
            frames = []
            for _ in range(_NUM_AMOSTRAS):
                frame = camera.snapshot()
                if frame is not None:
                    frames.append(frame)
                time.sleep(_INTERVALO_AMOSTRA_SEG)
        finally:
            camera.close()

        if not frames:
            return Answer(
                "Não consegui capturar nada da câmera -- confira se ela está livre "
                "(outro programa pode estar usando) e tente de novo.",
                Confidence.GUESS,
            )

        salvas = recognizer.enroll_frames(nome, frames)
        if salvas == 0:
            return Answer(
                f'Não encontrei nenhum rosto nítido nas fotos -- fique de frente pra câmera, '
                f'com boa luz, e tente "lembra esse rosto como {nome}" de novo.',
                Confidence.GUESS,
            )

        total = recognizer.sample_count(nome)
        aviso = ""
        if total < _MIN_AMOSTRAS_RECOMENDADO:
            aviso = f" Cadastrei poucas fotos boas ({total}) -- repita o comando mais uma vez pra melhorar a precisão."
        return Answer(
            f"Pronto, vou lembrar esse rosto como \"{nome}\" ({salvas} foto(s) nova(s), {total} no total).{aviso}",
            Confidence.CONFIRMED,
        )

    def _identificar(self):
        camera, recognizer, erro = self._preparar()
        if erro:
            return erro

        if not recognizer.known_names():
            return Answer(
                'Ainda não conheço nenhum rosto -- diga "lembra esse rosto como <nome>" '
                "pra eu aprender a reconhecer alguém.",
                Confidence.GUESS,
            )

        try:
            frame = camera.snapshot()
        finally:
            camera.close()

        if frame is None:
            return Answer("Não consegui capturar nada da câmera agora.", Confidence.GUESS)

        try:
            resultados = recognizer.identify(frame)
        except Exception as e:
            return Answer(f"Falha ao identificar: {e}", Confidence.GUESS)

        if not resultados:
            return Answer("Não vi nenhum rosto na câmera agora.", Confidence.GUESS)

        conhecidos = [r["nome"] for r in resultados if r["nome"] != "desconhecido"]
        if len(resultados) == 1:
            r = resultados[0]
            if r["nome"] == "desconhecido":
                return Answer(
                    "Vejo um rosto na câmera, mas não reconheço quem é.",
                    Confidence.GUESS,
                )
            return Answer(f"Isso aí é o(a) {r['nome']}.", Confidence.RELIABLE_SOURCE)

        if conhecidos:
            desconhecidos = len(resultados) - len(conhecidos)
            texto = f"Vejo {len(resultados)} rostos: {', '.join(conhecidos)}"
            if desconhecidos:
                texto += f" e {desconhecidos} que não reconheço"
            return Answer(texto + ".", Confidence.RELIABLE_SOURCE)
        return Answer(f"Vejo {len(resultados)} rostos, mas não reconheço nenhum deles.", Confidence.GUESS)

    def _esquecer(self, nome: str):
        if not nome:
            return Answer("Esquecer o rosto de quem?", Confidence.GUESS)
        from visao.faces import get_recognizer
        recognizer = get_recognizer()
        if recognizer.forget(nome):
            return Answer(f'Esqueci o rosto de "{nome}".', Confidence.CONFIRMED)
        return Answer(f'Eu não tinha nenhum rosto cadastrado como "{nome}".', Confidence.CONFIRMED)

    def _listar(self):
        from visao.faces import get_recognizer
        recognizer = get_recognizer()
        nomes = recognizer.known_names()
        if not nomes:
            return Answer('Ainda não conheço nenhum rosto -- diga "lembra esse rosto como <nome>".', Confidence.CONFIRMED)
        return Answer("Rostos que eu conheço: " + ", ".join(nomes) + ".", Confidence.CONFIRMED)
