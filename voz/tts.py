"""
voz/tts.py
============
Síntese de voz (texto -> fala). Usa `pyttsx3` (offline: SAPI5 no
Windows, NSSpeechSynthesizer no macOS, espeak no Linux) como motor
padrão -- nenhuma API externa envolvida.

Velocidade (`rate`, unidade "palavras por minuto" no estilo pyttsx3):
se não passada explicitamente, vem de `config.json` ->
`voz.velocidade_fala` (205 por padrão -- mais rápido que o default do
pyttsx3, ~175-200). Ajustável em tempo real por comando de chat
("fala mais rápido"/"fala mais devagar"/"velocidade normal da fala",
ver plugins/system_control.py).

Voz "robótica" (opcional, `robotic=True` ou config
`personalidade.voz_robotica`): no Windows, fala via SAPI5 direto
(`win32com`, parte do `pyttsx3[SAPI5]`/`pywin32` já instalado junto),
usando as tags de prosódia XML nativas da própria API (`<pitch>`,
`<rate>`) pra baixar o tom e deixar a fala mais grave e mecânica --
é um recurso padrão de engenharia de voz do Windows, não uma
imitação/clone de nenhuma voz específica de terceiros. Fora do Windows
(ou sem `pywin32`), cai para só reduzir a velocidade via `pyttsx3`,
sem controle de tom (SAPI5 é a única API aqui com esse recurso pronto
sem dependência nova).

Tom da voz robótica (`personalidade.tom_voz_robotica`, -9 por padrão
numa escala de -10 a 10 do próprio SAPI5): quando `robotic=True`,
também prefere uma voz MASCULINA entre as instaladas no mesmo idioma
(`_escolher_voz`) -- tom grave numa voz grave de base soa mais parecido
com uma IA "vilanesca" tipo Ultron do que o mesmo tom aplicado a uma
voz aguda. Continua sendo só seleção entre vozes JÁ instaladas no
Windows (nenhuma delas é clonada nem imita ninguém específico) -- se
não houver nenhuma voz masculina no idioma pedido, usa a que houver.
"""

import sys
import xml.sax.saxutils as saxutils

from logs.logger import get_logger

log = get_logger("voz")

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

try:
    import win32com.client
    HAS_SAPI_COM = sys.platform == "win32"
except ImportError:
    HAS_SAPI_COM = False

try:
    import numpy as _np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

_SVSFIsXML = 32  # flag do SAPI5 indicando que o texto passado é XML de prosódia, não texto puro
_SSFMCreateForWrite = 3  # modo do SAPI.SpFileStream pra escrever um WAV
_RATE_PADRAO = 205
_PITCH_ROBOTICO_PADRAO = -9


def _rate_para_sapi(rate: int) -> int:
    """Converte "palavras por minuto" (convenção pyttsx3) pra escala
    do SAPI5 (-10 a 10, 0 = ~180ppm) -- aproximação linear (cada
    unidade de Rate muda a velocidade em ~12ppm), suficiente pra dar
    a mesma sensação de "mais rápido/devagar" nas duas engines sem
    precisar calibrar cada voz instalada individualmente."""
    return max(-10, min(10, round((rate - 180) / 12)))


def _escolher_voz(voices, language_hint: str, preferir_masculina: bool):
    """Entre as vozes SAPI5 instaladas, escolhe a que bate com o idioma
    pedido -- e, se `preferir_masculina`, a mais grave/masculina entre
    essas (via GetAttribute("Gender"), quando o driver da voz expõe
    esse atributo; nem todo instalador de voz preenche isso, daí o
    try/except). Retorna None se nenhuma voz bater com o idioma --
    nesse caso quem chama não deve mexer em `.Voice`, deixando o
    default do próprio SAPI."""
    candidatas = [v for v in voices if language_hint.lower() in v.GetDescription().lower()]
    if not candidatas:
        return None
    if preferir_masculina:
        for v in candidatas:
            try:
                if v.GetAttribute("Gender").lower() == "male":
                    return v
            except Exception:
                continue
    return candidatas[0]


class TextToSpeech:
    def __init__(self, rate: int = None, voice_language_hint: str = "pt", robotic: bool = False, pitch: int = None):
        self._engine = None
        self._sapi = None
        if rate is None:
            from config.settings import get_settings
            rate = int(get_settings().get("voz.velocidade_fala", _RATE_PADRAO))
        if pitch is None:
            from config.settings import get_settings
            pitch = int(get_settings().get("personalidade.tom_voz_robotica", _PITCH_ROBOTICO_PADRAO))
        self.rate = rate
        self.pitch = max(-10, min(10, pitch))
        self.voice_language_hint = voice_language_hint
        self.robotic = robotic

    def available(self) -> bool:
        return HAS_PYTTSX3 or HAS_SAPI_COM

    def _ensure_engine(self):
        if self._engine is not None:
            return
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", self.rate)
        for voice in self._engine.getProperty("voices"):
            if self.voice_language_hint.lower() in (voice.id + voice.name).lower():
                self._engine.setProperty("voice", voice.id)
                break

    def _ensure_sapi(self):
        if self._sapi is not None:
            return
        self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
        self._sapi.Rate = _rate_para_sapi(self.rate)
        voz = _escolher_voz(self._sapi.GetVoices(), self.voice_language_hint, preferir_masculina=self.robotic)
        if voz is not None:
            self._sapi.Voice = voz

    def speak(self, text: str):
        if self.robotic and HAS_SAPI_COM:
            try:
                self._speak_robotic(text)
                return
            except Exception as e:
                log.warning("voz robótica (SAPI5 XML) falhou, caindo para voz normal: %s", e)
        if HAS_PYTTSX3:
            self._ensure_engine()
            self._engine.say(text)
            self._engine.runAndWait()
            return
        if HAS_SAPI_COM:
            # Sem pyttsx3, mas com SAPI5 disponível (Windows) -- fala
            # texto puro, sem a prosódia XML da voz robótica. Sem isso,
            # `available()` prometia funcionar (checa HAS_SAPI_COM) mas
            # `speak()` sempre levantava RuntimeError nesse cenário.
            self._ensure_sapi()
            self._sapi.Speak(text)
            return
        raise RuntimeError("Instale 'pyttsx3' para o Ultron falar (pip install pyttsx3).")

    def _speak_robotic(self, text: str):
        # Efeito "Ultron" (DSP): renderiza a fala grave num WAV e
        # pós-processa o áudio (camada detunada = "coro de vozes",
        # leve ring-mod = borda metálica, reverb curto = espaço frio,
        # soft-clip = peso/ameaça) antes de tocar. NÃO é clonagem da voz
        # de ninguém -- é a MESMA voz do sistema com efeitos de áudio por
        # cima, no ESTILO de uma IA vilanesca grave. Precisa de numpy +
        # SAPI (Windows); sem isso, cai pra prosódia XML simples abaixo.
        if self._efeito_ultron_disponivel():
            try:
                self._speak_ultron_dsp(text)
                return
            except Exception as e:
                log.warning("efeito Ultron (DSP) falhou, usando prosódia simples: %s", e)

        # Fallback: prosódia SAPI5 direta (pitch absoluto de -10 a 10,
        # 0 = padrão da voz), sem os efeitos de áudio. Combinado com
        # _ensure_sapi() preferindo uma voz masculina, já dá um tom
        # grave/mecânico -- só sem a camada/reverb do modo DSP.
        self._ensure_sapi()
        texto_seguro = saxutils.escape(text)
        xml = f'<pitch absmiddle="{self.pitch}"/><rate absspeed="{_rate_para_sapi(self.rate)}"/>{texto_seguro}'
        self._sapi.Speak(xml, _SVSFIsXML)

    # ---------- Efeito "Ultron" (processamento de áudio) ----------

    def _efeito_ultron_ligado(self) -> bool:
        from config.settings import get_settings
        return bool(get_settings().get("personalidade.efeito_ultron", True))

    def _intensidade_ultron(self) -> float:
        from config.settings import get_settings
        try:
            v = float(get_settings().get("personalidade.intensidade_ultron", 0.7))
        except (TypeError, ValueError):
            v = 0.7
        return max(0.0, min(1.0, v))

    def _efeito_ultron_disponivel(self) -> bool:
        return sys.platform == "win32" and HAS_SAPI_COM and HAS_NUMPY and self._efeito_ultron_ligado()

    def _speak_ultron_dsp(self, text: str):
        import os
        import tempfile
        import winsound

        bruto = tempfile.mktemp(suffix="_jarvis_raw.wav")
        processado = tempfile.mktemp(suffix="_jarvis_ultron.wav")
        try:
            samplerate, dados = self._render_sapi_wav(text, bruto)
            y = self._efeitos_ultron(dados, samplerate)
            self._escrever_wav(processado, y, samplerate)
            # SND_FILENAME = toca o arquivo; síncrono (sem SND_ASYNC) pra
            # encaixar na fila de fala do gui/app.py:_SpeakWorker, que
            # espera uma fala terminar antes de começar a próxima.
            winsound.PlaySound(processado, winsound.SND_FILENAME)
        finally:
            for caminho in (bruto, processado):
                try:
                    os.remove(caminho)
                except OSError:
                    pass

    def _render_sapi_wav(self, text: str, caminho: str):
        """Sintetiza a fala (com o pitch grave) num arquivo WAV via
        SAPI SpFileStream, em vez de tocar direto -- pra poder
        pós-processar. Retorna (samplerate, sinal float32 mono em -1..1).
        Usa uma SpVoice PRÓPRIA (não a self._sapi compartilhada) pra não
        deixar a saída redirecionada pro arquivo por engano depois."""
        import wave

        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(caminho, _SSFMCreateForWrite)
        try:
            voz = win32com.client.Dispatch("SAPI.SpVoice")
            escolhida = _escolher_voz(voz.GetVoices(), self.voice_language_hint, preferir_masculina=True)
            if escolhida is not None:
                voz.Voice = escolhida
            # No modo Ultron a entrega é mais DELIBERADA (um pouco mais
            # lenta que a fala normal) e no pitch MAIS GRAVE possível --
            # Ultron não tem pressa e fala do fundo do peito. O reforço de
            # graves/ressonância de verdade vem depois, em _efeitos_ultron.
            voz.Rate = max(-10, _rate_para_sapi(self.rate) - 2)
            pitch_ultron = max(-10, min(self.pitch, -10))
            voz.AudioOutputStream = stream
            texto_seguro = saxutils.escape(text)
            xml = f'<pitch absmiddle="{pitch_ultron}"/>{texto_seguro}'
            voz.Speak(xml, _SVSFIsXML)
        finally:
            stream.Close()

        with wave.open(caminho, "rb") as w:
            samplerate = w.getframerate()
            canais = w.getnchannels()
            largura = w.getsampwidth()
            cru = w.readframes(w.getnframes())
        if largura != 2:
            raise RuntimeError(f"WAV do SAPI não veio em 16-bit (sampwidth={largura}).")
        sinal = _np.frombuffer(cru, dtype=_np.int16).astype(_np.float32) / 32768.0
        if canais == 2:
            sinal = sinal.reshape(-1, 2).mean(axis=1)
        return samplerate, sinal

    @staticmethod
    def _suavizar(sig, largura: int):
        """Passa-baixa simples via média móvel ponderada (janela de
        Hann) -- usado tanto pra reforçar graves (janela larga) quanto
        pra tirar a aspereza dos agudos (janela estreita). Sem recursão/
        IIR, então não tem risco de instabilidade nem artefato de fase."""
        largura = max(2, int(largura))
        k = _np.hanning(largura)
        soma = k.sum()
        if soma <= 0:
            return sig
        return _np.convolve(sig, (k / soma).astype(_np.float32), mode="same").astype(_np.float32)

    def _efeitos_ultron(self, x, samplerate: int):
        """Cadeia de efeitos que dá o caráter "Ultron": grave, quente,
        ressonante, em camadas e ligeiramente metálico -- SEM virar robô
        de brinquedo. Intensidade regulável por
        `personalidade.intensidade_ultron` (0..1). Mantém a fala
        inteligível de propósito.

        Ordem pensada como uma cadeia de estúdio: doblagem/coro ->
        reforço de graves (corpo) -> suavização de agudos (tira o
        chiado) -> sheen metálico sutil -> saturação (peso) -> reverb
        cinematográfico -> normalização."""
        intens = self._intensidade_ultron()
        n = len(x)
        if n == 0 or intens <= 0:
            return x
        indices = _np.arange(n)
        t = indices / float(samplerate)

        # 1) DOBLAGEM/CORO -- o "mais-que-humano". Duas cópias levemente
        #    detunadas (±10 cents, sutil pra não soar desafinado) somadas
        #    por baixo, dão largura e a sensação de "várias vozes numa".
        def _detune(sig, cents):
            r = 2 ** (cents / 1200.0)
            origem = _np.clip(indices * r, 0, n - 1)
            return _np.interp(origem, indices, sig).astype(_np.float32)

        coro = 0.4 * intens * (_detune(x, 10.0) + _detune(x, -10.0))
        y = x + coro

        # 2) CORPO/GRAVES -- reforça a região grave (uma passa-baixa larga
        #    somada de volta) pra dar aquele peito ressonante de IA
        #    gigante, em vez de uma voz fininha de sintetizador.
        graves = self._suavizar(y, samplerate * 0.006)  # ~ até ~150-250 Hz
        y = y + graves * (0.7 * intens)

        # 3) TIRA A ASPEREZA -- uma passa-baixa MUITO estreita misturada
        #    de leve arredonda os agudos sibilantes/metálicos ("ss", "ch")
        #    que soam artificiais no TTS, deixando a voz mais "analógica".
        y = y * (1 - 0.25 * intens) + self._suavizar(y, samplerate * 0.0006) * (0.25 * intens)

        # 4) SHEEN METÁLICO sutil -- ring-mod bem baixo (portadora grave,
        #    ~48 Hz) dá um brilho de "máquina" sem virar Dalek buzzento.
        ring = y * _np.sin(2 * _np.pi * 48.0 * t).astype(_np.float32)
        mix_ring = 0.12 * intens
        y = y * (1 - mix_ring) + ring * mix_ring

        # 5) SATURAÇÃO -- soft-clip dá peso/ameaça e "cola" as camadas,
        #    sem estourar (tanh limita naturalmente).
        y = _np.tanh(y * (1.0 + 1.4 * intens))

        # 6) REVERB CINEMATOGRÁFICO -- mais taps que antes, decaindo mais
        #    longo, pra um espaço frio e grande (sala de servidores) em
        #    vez de um eco curtinho de quarto.
        cauda = _np.zeros_like(y)
        for atraso_ms, ganho in ((37, 0.30), (73, 0.24), (115, 0.18), (170, 0.12), (240, 0.07)):
            d = int(samplerate * atraso_ms / 1000.0)
            if 0 < d < n:
                eco = _np.zeros_like(y)
                eco[d:] = y[:-d]
                cauda = cauda + eco * ganho
        y = y + cauda * intens

        pico = float(_np.max(_np.abs(y))) or 1.0
        return (y / pico) * 0.95

    def _escrever_wav(self, caminho: str, y, samplerate: int):
        import wave

        pcm = (_np.clip(y, -1.0, 1.0) * 32767).astype(_np.int16).tobytes()
        with wave.open(caminho, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(samplerate)
            w.writeframes(pcm)
