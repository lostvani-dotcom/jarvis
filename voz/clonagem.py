"""
voz/clonagem.py
==================
Clonagem da voz do PRÓPRIO usuário (não de terceiros -- ver aviso
abaixo) via XTTS v2 (Coqui TTS -- pacote `coqui-tts` no PyPI, o fork
mantido do projeto `TTS` original, que foi descontinuado). Zero-shot:
sintetiza qualquer texto na voz de alguém a partir de só alguns
segundos de amostra de áudio dessa pessoa, sem precisar treinar nada.

Uso ético (deliberado): só existe comando de chat pra gravar a PRÓPRIA
voz (ver plugins/clonagem_voz.py, "grava minha voz"), nunca a de
outra pessoa -- clonar a voz de alguém sem consentimento é o tipo de
coisa que este projeto evita de propósito (mesma postura de
voz/tts.py sobre a voz "robótica" nunca ser clonagem de ninguém real).
Se quiser usar a voz de outra pessoa, grave você mesmo a amostra com o
consentimento dela -- este módulo não distingue tecnicamente entre "é
sua voz" e "não é", a fronteira aqui é de uso, não de código.

Modelo: `tts_models/multilingual/multi-dataset/xtts_v2` -- baixado
sozinho (~1.8GB) na primeira síntese, cacheado localmente (não baixa
de novo depois). Licença do modelo pré-treinado: Coqui Public Model
License (CPML) -- gratuita pra uso pessoal/pesquisa, como este; uso
comercial exigiria licença própria da Coqui.

Degrada graciosamente: sem `coqui-tts` instalado (`pip install
"coqui-tts[cpu]"`, ver requirements-voz.txt -- pacote pesado, opcional
de propósito) ou sem amostra gravada ainda, `disponivel()` retorna
False e o resto do Ultron continua funcionando normal, com a voz
padrão/robótica de sempre.
"""

import importlib.util
import os

from logs.logger import get_logger

log = get_logger("voz")

HAS_COQUI_TTS = importlib.util.find_spec("TTS") is not None

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AMOSTRA_DIR = os.path.join(_BASE_DIR, "data", "voz_clonada")
_AMOSTRA_PATH = os.path.join(_AMOSTRA_DIR, "amostra.wav")
_AUDIOS_GERADOS_DIR = os.path.join(_BASE_DIR, "data", "audios_gerados")
_MODELO_XTTS = "tts_models/multilingual/multi-dataset/xtts_v2"
_SAMPLERATE_GRAVACAO = 22050  # amostragem que o XTTS espera pra referência
DURACAO_AMOSTRA_PADRAO = 20.0  # segundos -- o suficiente pro clone soar bem, sem cansar quem está gravando; público (plugins/clonagem_voz.py usa pra avisar antes de gravar)
_PICO_MINIMO_CONFIAVEL = 0.01  # abaixo disso (escala float -1..1), a gravação foi silêncio/quase nada


def disponivel() -> bool:
    return HAS_COQUI_TTS


def tem_amostra() -> bool:
    return os.path.isfile(_AMOSTRA_PATH)


def gravar_amostra(duracao_segundos: float = DURACAO_AMOSTRA_PADRAO, device_index: int = None) -> dict:
    """Grava `duracao_segundos` de áudio do microfone e salva como
    amostra de referência pra clonagem. BLOQUEIA a thread que chamou
    pela duração inteira -- mesmo padrão de
    plugins/reconhecimento_facial.py ao cadastrar um rosto: é um
    comando explícito do usuário, que já foi avisado antes (ver
    plugins/clonagem_voz.py) que a gravação vai demorar esse tempo.
    Retorna {"sucesso": bool, "motivo": str|None}."""
    try:
        import sounddevice as sd
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        return {"sucesso": False, "motivo": f"falta instalar uma dependência de áudio ({e})"}

    os.makedirs(_AMOSTRA_DIR, exist_ok=True)
    try:
        audio = sd.rec(
            int(duracao_segundos * _SAMPLERATE_GRAVACAO),
            samplerate=_SAMPLERATE_GRAVACAO, channels=1, dtype="float32", device=device_index,
        )
        sd.wait()
    except Exception as e:
        return {"sucesso": False, "motivo": f"falha ao gravar do microfone ({e})"}

    pico = float(np.max(np.abs(audio))) if audio.size else 0.0
    if pico < _PICO_MINIMO_CONFIAVEL:
        return {"sucesso": False, "motivo": "não captei quase nenhum som -- confira o microfone e tente de novo"}

    sf.write(_AMOSTRA_PATH, audio, _SAMPLERATE_GRAVACAO)
    return {"sucesso": True, "motivo": None}


def esquecer_amostra() -> bool:
    if not tem_amostra():
        return False
    os.remove(_AMOSTRA_PATH)
    return True


class VoiceCloner:
    """Encapsula o modelo XTTS -- carregado sob demanda (é pesado,
    costuma levar dezenas de segundos na primeira síntese) e
    reaproveitado depois (ver get_cloner())."""

    def __init__(self):
        self._tts = None

    def disponivel(self) -> bool:
        return HAS_COQUI_TTS and tem_amostra()

    def _garantir_modelo(self):
        if self._tts is not None:
            return
        import os as _os

        # O XTTS pede confirmação INTERATIVA (input() no terminal) da
        # licença do modelo pré-treinado (CPML) no primeiro download --
        # isso travaria pra sempre aqui dentro (chamado de dentro de um
        # comando de chat, sem terminal interativo nenhum). A própria
        # lib documenta essa variável de ambiente como o jeito
        # oficial de pré-aceitar em contexto não-interativo (ver
        # TTS.utils.manage.ModelManager.tos_agreed) -- aceitamos em
        # nome do usuário porque ele já pediu explicitamente pra clonar
        # a PRÓPRIA voz (ver plugins/clonagem_voz.py), mas a licença
        # continua sempre citada aqui e na resposta do comando, nunca
        # escondida: Coqui Public Model License (CPML), gratuita pra
        # uso pessoal/não-comercial -- https://coqui.ai/cpml
        _os.environ.setdefault("COQUI_TOS_AGREED", "1")

        from TTS.api import TTS
        log.info("carregando modelo XTTS v2 (pode baixar ~1.8GB na primeira vez)...")
        self._tts = TTS(_MODELO_XTTS)

    def sintetizar(self, texto: str, idioma: str = "pt", saida: str = None) -> str:
        """Sintetiza `texto` na voz clonada, salva um WAV e retorna o
        caminho -- quem chama é responsável por apagar o arquivo depois
        de tocar (ver voz/tts.py:_speak_clonada). `idioma` no formato
        do XTTS (2 letras: "pt", "en"...)."""
        if not self.disponivel():
            raise RuntimeError("Clonagem de voz indisponível (sem coqui-tts instalado ou sem amostra gravada).")
        self._garantir_modelo()
        if saida is None:
            import tempfile
            saida = tempfile.mktemp(suffix="_ultron_voz_clonada.wav")
        self._tts.tts_to_file(text=texto, speaker_wav=_AMOSTRA_PATH, language=idioma[:2], file_path=saida)
        return saida

    def gerar_arquivo_compartilhavel(self, texto: str, idioma: str = "pt") -> str:
        """Como `sintetizar()`, mas salva num arquivo PERSISTENTE em
        `data/audios_gerados/` (em vez de um temporário que quem chama
        deveria apagar) -- pensado pra ser anexado/enviado manualmente
        em outro app (WhatsApp, Telegram, e-mail, etc.), não só tocado
        na hora pelo alto-falante. Retorna o caminho do arquivo."""
        import re
        import time

        os.makedirs(_AUDIOS_GERADOS_DIR, exist_ok=True)
        pedaco = re.sub(r"[^\w\- ]", "", texto)[:40].strip().replace(" ", "_") or "audio"
        nome = f"{int(time.time())}_{pedaco}.wav"
        caminho = os.path.join(_AUDIOS_GERADOS_DIR, nome)
        return self.sintetizar(texto, idioma=idioma, saida=caminho)


_cloner_padrao = None


def get_cloner() -> VoiceCloner:
    """Instância compartilhada -- reaproveita o modelo XTTS já
    carregado em memória entre falas, em vez de recarregar (pesado) a
    cada resposta."""
    global _cloner_padrao
    if _cloner_padrao is None:
        _cloner_padrao = VoiceCloner()
    return _cloner_padrao
