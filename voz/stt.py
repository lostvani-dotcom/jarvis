"""
voz/stt.py
============
Reconhecimento de voz (fala -> texto). Tenta, em ordem de preferência
(offline primeiro):
  1. `vosk` (totalmente offline, modelos pequenos)
  2. `faster-whisper` (offline, mais pesado, mais preciso)
  3. `speech_recognition` (usa o reconhecedor gratuito do Google por
     padrão, que é uma API ONLINE -- só é usado se as opções offline
     acima não estiverem instaladas, e isso fica explícito no status)

Todos exigem capturar áudio do microfone via `sounddevice`. Sem essa
lib (ou sem microfone), `available()` retorna False.

Detecção de silêncio (melhoria): `vosk`/`faster-whisper` gravavam por
uma duração FIXA sempre (ex.: sempre esperava os 5 segundos inteiros,
mesmo se você falasse uma frase curta e parasse em 1s) -- agora
`_gravar_ate_silencio()` grava em streaming e para sozinho assim que
detecta silêncio depois de você falar (config
`voz.silencio_para_parar_segundos`, 1s por padrão), com um teto de
segurança (`duracao_maxima_comando_segundos`) pra nunca ficar preso
gravando pra sempre. `speech_recognition` já fazia isso nativamente
(`Recognizer.listen()`), por isso não precisou de mudança.

Melhorias adicionais:
- **Redução de ruído** (opcional, `noisereduce`): aplicada no áudio
  gravado antes de transcrever, se a lib estiver instalada -- sem ela,
  transcreve o áudio bruto normalmente (degrada graciosamente).
- **Aviso de qualidade baixa**: `listen_and_transcribe_detalhado()`
  calcula se o trecho gravado tem volume/duração suficiente pra uma
  transcrição confiável, e avisa em vez de devolver um texto vazio/
  errado silenciosamente. `listen_and_transcribe()` continua existindo
  (compatibilidade com quem já chama), só devolve o texto puro.
- **Idioma automático**: com `faster-whisper` (único motor aqui que
  tem detecção de idioma de verdade embutida), `language="auto"`
  detecta sozinho em vez de assumir um idioma fixo. `vosk` e o
  fallback online continuam precisando de um idioma configurado --
  cada modelo do vosk já É de um idioma específico, não tem como
  "auto-detectar" sem carregar vários modelos ao mesmo tempo (custo
  alto demais pra valer a pena aqui).
"""

import importlib.util

from config.settings import get_settings
from logs.logger import get_logger

log = get_logger("voz")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

try:
    import vosk
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False

try:
    import speech_recognition as sr
    HAS_SPEECH_RECOGNITION = True
except ImportError:
    HAS_SPEECH_RECOGNITION = False

# faster-whisper e noisereduce são MUITO lentos de IMPORTAR de verdade
# (~15-20 SEGUNDOS cada, medido -- puxam ctranslate2/scipy por baixo),
# mesmo quando nem chegam a ser o motor usado (vosk, já instalado, é
# preferido e é rápido). Antes isso rodava aqui em cima, no import do
# módulo -- ou seja, TODA abertura do Ultron pagava ~35s de import
# parado antes até da tela aparecer (era a causa real de "o Ultron não
# abre": ele abria, só demorava demais sem dar nenhum sinal). Por isso
# só checamos se estão INSTALADOS (find_spec -- olha se o pacote existe
# sem executar o módulo, é rápido) aqui; o import de verdade só
# acontece dentro de _listen_whisper()/_reduzir_ruido(), na hora que
# forem genuinamente usados.
HAS_FASTER_WHISPER = importlib.util.find_spec("faster_whisper") is not None
HAS_NOISEREDUCE = importlib.util.find_spec("noisereduce") is not None

_RMS_MINIMO_CONFIAVEL = 300.0  # abaixo disso (escala int16), a fala captada foi baixa demais pra confiar


def _has_input_device() -> bool:
    """Verifica se o Windows/SO enxerga algum microfone de verdade --
    sem isso, `backend_disponivel()` reportaria as libs como
    disponíveis (elas só checam se o pacote foi importado), e o erro
    real (PortAudioError opaco) só apareceria depois, no meio da
    conversa, ao tentar gravar. Falhar cedo aqui dá uma mensagem clara
    ("verifique o microfone") em vez de um traceback confuso."""
    if not HAS_SOUNDDEVICE:
        return True  # sem sounddevice não há como checar por aqui -- deixa o erro real aparecer na hora de gravar
    try:
        sd.query_devices(kind="input")
        return True
    except Exception:
        return False


class SpeechToText:
    def __init__(self, language: str = "pt-BR", engine: str = "auto"):
        self.language = language
        self.engine = engine
        self._vosk_model = None
        self._whisper_model = None

    def backend_disponivel(self) -> str:
        if not _has_input_device():
            return ""
        if self.engine in ("auto", "vosk") and HAS_VOSK and HAS_SOUNDDEVICE:
            return "vosk"
        if self.engine in ("auto", "whisper") and HAS_FASTER_WHISPER and HAS_SOUNDDEVICE:
            return "faster-whisper"
        if self.engine in ("auto", "google") and HAS_SPEECH_RECOGNITION:
            return "speech_recognition (online, Google)"
        return ""

    def available(self) -> bool:
        return bool(self.backend_disponivel())

    def listen_and_transcribe(self, duration_seconds: float = 5.0) -> str:
        """Compatibilidade com quem já chama isto esperando só o texto
        -- ver listen_and_transcribe_detalhado() pra qualidade/idioma
        detectado."""
        return self.listen_and_transcribe_detalhado(duration_seconds)["texto"]

    def listen_and_transcribe_detalhado(self, duration_seconds: float = 5.0) -> dict:
        """Retorna {"texto", "confiavel", "motivo", "idioma_detectado"}.
        `confiavel=False` significa que o trecho gravado foi curto/
        baixo demais pra confiar na transcrição (`motivo` explica) --
        `texto` ainda vem preenchido com o melhor palpite do motor,
        nunca None, então quem chama pode decidir ignorar ou não."""
        backend = self.backend_disponivel()
        if not backend:
            raise RuntimeError(
                "Nenhum motor de reconhecimento de voz disponível. Instale "
                "'vosk', 'faster-whisper' ou 'SpeechRecognition' + 'sounddevice' "
                "(ver requirements-voz.txt)."
            )
        if backend == "vosk":
            return self._listen_vosk(duration_seconds)
        if backend == "faster-whisper":
            return self._listen_whisper(duration_seconds)
        return self._listen_speech_recognition()

    def _gravar_ate_silencio(self, duracao_maxima: float, samplerate: int = 16000):
        """Grava em streaming (blocos de 30ms) e para sozinho assim que
        detecta `voz.silencio_para_parar_segundos` de silêncio DEPOIS
        de ter detectado fala -- em vez de sempre gravar a duração
        máxima inteira, mesmo quando a pessoa já parou de falar.

        Retorna (audio, samplerate, metadados) -- metadados tem "falou"
        e "rms_max", usados por _avaliar_qualidade() pra decidir se dá
        pra confiar na transcrição."""
        import numpy as np

        settings = get_settings()
        silencio_seg = float(settings.get("voz.silencio_para_parar_segundos", 1.0))
        duracao_minima = min(0.6, duracao_maxima)  # nunca corta na respiração inicial
        limiar_rms = 500.0  # empírico p/ int16 -- ambiente silencioso fica bem abaixo disso

        bloco_seg = 0.03
        tamanho_bloco = max(1, int(samplerate * bloco_seg))
        blocos = []
        falou = False
        rms_max = 0.0
        silencio_acumulado = 0.0
        tempo_total = 0.0

        with sd.InputStream(samplerate=samplerate, channels=1, dtype="int16", blocksize=tamanho_bloco) as stream:
            while tempo_total < duracao_maxima:
                bloco, _overflow = stream.read(tamanho_bloco)
                blocos.append(bloco.copy())
                tempo_total += bloco_seg
                rms = float(np.sqrt(np.mean(bloco.astype("float64") ** 2))) if bloco.size else 0.0
                rms_max = max(rms_max, rms)
                if rms >= limiar_rms:
                    falou = True
                    silencio_acumulado = 0.0
                else:
                    silencio_acumulado += bloco_seg
                if tempo_total >= duracao_minima and falou and silencio_acumulado >= silencio_seg:
                    break

        metadados = {"falou": falou, "rms_max": rms_max, "duracao_segundos": tempo_total}
        if not blocos:
            return np.zeros((0, 1), dtype="int16"), samplerate, metadados
        return np.concatenate(blocos), samplerate, metadados

    def _avaliar_qualidade(self, metadados: dict) -> tuple:
        """(confiavel: bool, motivo: str|None) -- heurística simples:
        precisa ter detectado fala de verdade E com volume razoável.
        Não é análise espectral nem detecção de clipping/distorção de
        verdade, só um filtro honesto pro caso óbvio de "praticamente
        não captou nada"."""
        if not metadados["falou"]:
            return False, "não detectei fala (silêncio ou volume baixo demais)"
        if metadados["rms_max"] < _RMS_MINIMO_CONFIAVEL:
            return False, "volume captado foi baixo demais pra uma transcrição confiável"
        return True, None

    def _reduzir_ruido(self, audio, samplerate: int):
        """Aplica redução de ruído (noisereduce) se a lib estiver
        disponível -- sem ela, retorna o áudio bruto sem modificar
        (degrada graciosamente, nunca impede a transcrição)."""
        if not HAS_NOISEREDUCE or audio.size == 0:
            return audio
        try:
            import noisereduce as nr
            import numpy as np
            audio_float = audio.astype("float32").flatten() / 32768.0
            reduzido = nr.reduce_noise(y=audio_float, sr=samplerate)
            return (reduzido * 32768.0).astype("int16").reshape(-1, 1)
        except Exception as e:
            log.warning("redução de ruído falhou, usando áudio original: %s", e)
            return audio

    def _listen_vosk(self, duration_seconds: float) -> dict:
        import json as _json
        audio, samplerate, metadados = self._gravar_ate_silencio(duration_seconds)
        confiavel, motivo = self._avaliar_qualidade(metadados)
        audio = self._reduzir_ruido(audio, samplerate)
        if self._vosk_model is None:
            try:
                self._vosk_model = vosk.Model(lang="pt" if self.language.startswith("pt") else "en-us")
            except Exception as e:
                raise RuntimeError(
                    f"Não consegui carregar o modelo do vosk ({e}). Confira sua conexão na "
                    "primeira vez (o modelo é baixado automaticamente), ou baixe manualmente "
                    "em alphacephei.com/vosk/models."
                ) from e
        rec = vosk.KaldiRecognizer(self._vosk_model, samplerate)
        rec.AcceptWaveform(audio.tobytes())
        result = _json.loads(rec.FinalResult())
        return {
            "texto": result.get("text", ""),
            "confiavel": confiavel,
            "motivo": motivo,
            "idioma_detectado": None,  # vosk não detecta idioma -- o modelo carregado já é fixo
        }

    def _listen_whisper(self, duration_seconds: float) -> dict:
        from faster_whisper import WhisperModel

        audio, samplerate, metadados = self._gravar_ate_silencio(duration_seconds)
        confiavel, motivo = self._avaliar_qualidade(metadados)
        audio = self._reduzir_ruido(audio, samplerate)
        if self._whisper_model is None:
            self._whisper_model = WhisperModel("small", device="cpu")
        audio_float = (audio.astype("float32") / 32768.0).flatten()
        idioma = None if self.language in ("auto", None) else self.language[:2]
        segments, info = self._whisper_model.transcribe(audio_float, language=idioma)
        texto = " ".join(seg.text for seg in segments).strip()
        return {
            "texto": texto,
            "confiavel": confiavel,
            "motivo": motivo,
            "idioma_detectado": getattr(info, "language", idioma),
        }

    def _listen_speech_recognition(self) -> dict:
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source)
        try:
            texto = recognizer.recognize_google(audio, language=self.language)
            return {"texto": texto, "confiavel": True, "motivo": None, "idioma_detectado": None}
        except sr.UnknownValueError:
            return {
                "texto": "",
                "confiavel": False,
                "motivo": "não entendi o áudio (fala baixa, ruído ou idioma diferente do configurado)",
                "idioma_detectado": None,
            }
