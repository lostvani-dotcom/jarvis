"""
voz/loop.py
=============
VoiceLoop: laço de conversa contínua por voz -- ouvir, transcrever,
processar no Ultron, falar a resposta. Usado por `main.py --voz`.

Configuração lida automaticamente de `config.json` quando não
passada explicitamente no construtor:
  - `voz.ativar_wakeword` / `voz.palavra_chave` / `voz.palavras_chave`:
    liga a palavra de ativação ("jarvis, que horas são" em vez de
    precisar reiniciar o modo voz pra cada frase) -- `palavras_chave`
    (lista) permite mais de uma, ex. `["jarvis", "ark"]`, além de
    `palavra_chave` (singular, continua funcionando) -- ver
    voz/wakeword.py.
  - `personalidade.voz_robotica`: tom de voz mais grave/mecânico via
    SAPI5 (ver voz/tts.py) -- não é clonagem de nenhuma voz de
    terceiros, só prosódia (pitch/rate) da própria API do Windows.
  - `voz.motor_stt`: escolhe o motor de reconhecimento ("auto", "vosk",
    "whisper" ou "google", ver voz/stt.py:backend_disponivel) --
    BUG CORRIGIDO: essa chave existia no config.json mas nunca era
    lida de verdade aqui (`SpeechToText` sempre nascia com
    `engine="auto"`, então escolher "whisper" no config.json não tinha
    nenhum efeito). Agora é passada pro `SpeechToText` de verdade.
  - `voz.conversa_continua_segundos`: depois de responder, se a
    palavra de ativação estiver ligada, o Ultron continua ouvindo por
    esse tanto de tempo SEM exigir a palavra de novo (só ela quebra o
    "preciso dizer jarvis toda frase" de uma conversa de verdade) --
    ver `_ouvir_turno()`. Fica em silêncio por essa janela e a próxima
    fala volta a exigir a palavra de ativação. `0` desliga esse
    comportamento (sempre exige a palavra, modo antigo).

Saudação por reconhecimento facial (opt-in, `personalidade.
saudacao_por_rosto`, desligado por padrão): quando a palavra de
ativação acabou de ser dita (início de uma conversa nova -- nunca no
meio da janela de conversa contínua, nem sem wakeword, câmera ligando
a cada frase seria intrusivo demais), tira uma foto rápida e, se
reconhecer alguém já cadastrado (ver plugins/reconhecimento_facial.py),
prefixa a resposta falada com "Oi, <nome>!". Melhor-esforço: qualquer
falha (sem câmera, sem opencv-contrib, ninguém reconhecido) some em
silêncio, nunca atrapalha a conversa.

Interromper o Ultron no meio da fala: enquanto ele fala a resposta, um
monitor de microfone concorrente (`_falar_com_interrupcao`) fica de
olho no volume captado -- se detectar você falando por cima (qualquer
fala, não precisa de uma palavra específica tipo "para"), a fala é
cortada na hora (`voz/tts.py:TextToSpeech.parar()`) e o próximo turno
já ouve direto o que você quis dizer, sem exigir a palavra de ativação
de novo. Limitação honesta: sem cancelamento de eco -- em volume alto
ou microfone sensível, o próprio áudio do Ultron pode disparar uma
interrupção falsa; funciona melhor com fone de ouvido ou volume
moderado. Precisa de `sounddevice`; sem ele, a fala simplesmente não
pode ser interrompida (comportamento de sempre).
"""

import re

from config.settings import get_settings
from logs.logger import get_logger
from voz.stt import SpeechToText
from voz.tts import TextToSpeech
from voz.wakeword import WakeWordDetector

log = get_logger("voz")

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

# Frases que encerram a janela de conversa contínua na hora (em vez de
# esperar o silêncio expirar sozinho) -- "é só isso, obrigado" não devia
# precisar de mais uma pausa até o Ultron voltar a exigir a palavra de
# ativação.
_FRASES_ENCERRAR_CONVERSA = re.compile(
    r"^\s*(é\s+)?só\s+isso\b|^\s*(muito\s+)?obrigad[oa]\b|^\s*pode\s+parar\b|^\s*(é\s+)?isso\s+a[íi]\b",
    re.IGNORECASE,
)


class VoiceLoop:
    def __init__(self, jarvis, keyword: str = None, keywords: list = None, language: str = "pt-BR",
                 use_wakeword: bool = None, robotic: bool = None):
        settings = get_settings()
        if keyword is None and keywords is None:
            keyword = settings.get("voz.palavra_chave", "jarvis")
            keywords = settings.get("voz.palavras_chave", [])
        if use_wakeword is None:
            use_wakeword = settings.get("voz.ativar_wakeword", False)
        if robotic is None:
            robotic = settings.get("personalidade.voz_robotica", False)
        self._duracao_maxima_comando = float(settings.get("voz.duracao_maxima_comando_segundos", 12.0))
        self._conversa_continua_seg = float(settings.get("voz.conversa_continua_segundos", 18.0))

        self.jarvis = jarvis
        self.stt = SpeechToText(language=language, engine=settings.get("voz.motor_stt", "auto"))
        self.tts = TextToSpeech(robotic=bool(robotic))
        self.wakeword = WakeWordDetector(keyword=keyword, keywords=keywords, stt=self.stt) if use_wakeword else None

    def available(self) -> bool:
        return self.stt.available() and self.tts.available()

    def _ouvir_comando(self) -> str:
        """Um turno de escuta: com palavra de ativação, aceita tanto
        "jarvis, comando" numa respiração só quanto "jarvis" seguido de
        uma pausa e o comando depois; sem palavra de ativação, ouve
        direto. A gravação em si para sozinha quando detecta silêncio
        (ver voz/stt.py:_gravar_ate_silencio) -- `_duracao_maxima_comando`
        é só o teto de segurança, não uma espera fixa."""
        if not (self.wakeword and self.wakeword.available()):
            print("Ouvindo...")
            return self.stt.listen_and_transcribe(duration_seconds=self._duracao_maxima_comando)

        print("Aguardando palavra-chave...")
        resto = self.wakeword.listen_for_command()
        if resto is None:
            return ""
        if resto:
            return resto
        print("Ouvindo o comando...")
        return self.stt.listen_and_transcribe(duration_seconds=self._duracao_maxima_comando)

    def _em_janela_de_conversa(self) -> bool:
        """Só faz sentido ter uma janela de conversa contínua quando HÁ
        palavra de ativação pra "pular" -- sem wakeword, o loop já ouve
        direto a cada turno, então já é "contínuo" por natureza."""
        return bool(self.wakeword and self.wakeword.available()) and self._conversa_continua_seg > 0

    def _falar_com_interrupcao(self, texto: str) -> bool:
        """Fala `texto`, mas com um monitor de microfone concorrente
        vigiando se você começa a falar por cima -- se sim, para a
        fala na hora (TextToSpeech.parar()) e retorna True, pra quem
        chama já tratar o próximo turno como uma escuta direta (sem
        exigir a palavra de ativação), em vez de esperar a fala
        terminar sozinha. Sem `sounddevice`, cai pra `self.tts.speak()`
        normal (sem chance de interromper) -- ver docstring do módulo
        pra limitação honesta sobre eco."""
        if not HAS_SOUNDDEVICE:
            self.tts.speak(texto)
            return False

        import threading

        interrompido = threading.Event()
        parar_monitor = threading.Event()
        device_index = getattr(self.stt, "device_index", None)

        def _monitorar():
            import numpy as np

            samplerate = 16000
            tamanho_bloco = int(samplerate * 0.03)
            # Limiar mais alto que o da gravação normal de propósito --
            # o alto-falante tocando a própria fala do Ultron pode
            # vazar pro microfone; exigir mais volume E mais blocos
            # seguidos (não só um pico único) reduz falso positivo.
            limiar_rms = 1100.0
            blocos_necessarios = 5  # ~150ms de som sustentado acima do limiar
            contagem = 0
            try:
                with sd.InputStream(
                    samplerate=samplerate, channels=1, dtype="int16",
                    blocksize=tamanho_bloco, device=device_index,
                ) as stream:
                    while not parar_monitor.is_set():
                        bloco, _overflow = stream.read(tamanho_bloco)
                        rms = float(np.sqrt(np.mean(bloco.astype("float64") ** 2))) if bloco.size else 0.0
                        if rms >= limiar_rms:
                            contagem += 1
                            if contagem >= blocos_necessarios:
                                interrompido.set()
                                return
                        else:
                            contagem = 0
            except Exception as e:
                log.warning("monitor de interrupção da fala falhou: %s", e)

        thread_monitor = threading.Thread(target=_monitorar, daemon=True)
        thread_monitor.start()

        thread_fala = threading.Thread(target=lambda: self.tts.speak(texto), daemon=True)
        thread_fala.start()

        while thread_fala.is_alive():
            if interrompido.is_set():
                self.tts.parar()
                break
            thread_fala.join(timeout=0.08)

        parar_monitor.set()
        thread_monitor.join(timeout=1.0)
        return interrompido.is_set()

    def _saudacao_por_rosto(self) -> str:
        """Ver docstring do módulo -- só chamada no início de uma
        conversa nova (wake word recém-dita). Retorna "Oi, <nome>! "
        se reconhecer alguém, ou "" (silenciosamente) em qualquer outro
        caso -- desligado, sem câmera, sem ninguém cadastrado, ninguém
        reconhecido na foto."""
        settings = get_settings()
        if not settings.get("personalidade.saudacao_por_rosto", False):
            return ""
        try:
            from visao.camera import Camera
            from visao.faces import get_recognizer

            recognizer = get_recognizer()
            if not recognizer.available() or not recognizer.known_names():
                return ""
            camera = Camera()
            if not camera.available():
                return ""
            try:
                frame = camera.snapshot()
            finally:
                camera.close()
            if frame is None:
                return ""
            nomes = [r["nome"] for r in recognizer.identify(frame) if r["nome"] != "desconhecido"]
            return f"Oi, {nomes[0]}! " if nomes else ""
        except Exception as e:
            log.warning("falha na saudação por rosto: %s", e)
            return ""

    def _ouvir_turno(self, aguardando_wakeword: bool) -> str:
        """Um turno de escuta. Com `aguardando_wakeword=False` (dentro
        da janela de conversa contínua), ouve DIRETO, sem exigir a
        palavra de ativação de novo -- mesma lógica de "follow-up mode"
        de assistentes de voz comuns (fala uma vez com "jarvis", depois
        conversa por alguns segundos sem repetir o nome)."""
        if not aguardando_wakeword:
            print(f"Ouvindo (conversa contínua, {self._conversa_continua_seg:.0f}s)...")
            return self.stt.listen_and_transcribe(duration_seconds=self._conversa_continua_seg)
        return self._ouvir_comando()

    def run(self, max_turns: int = None):
        if not self.available():
            raise RuntimeError(
                "Voz indisponível: instale as dependências de voz "
                "(ver requirements-voz.txt) e verifique o microfone."
            )

        modo = f'com palavra de ativação "{self.wakeword.keyword}"' if self.wakeword else "sem palavra de ativação"
        if self._em_janela_de_conversa():
            modo += f" + conversa contínua ({self._conversa_continua_seg:.0f}s sem precisar repetir a palavra)"
        print(f"Ultron (modo voz, {modo}) pronto. Fale normalmente. Ctrl+C para sair.")
        turns = 0
        aguardando_wakeword = True
        while max_turns is None or turns < max_turns:
            try:
                # Guardado ANTES de _ouvir_turno mudar de estado --
                # "conversa nova" é exatamente "estava exigindo a
                # wakeword e ela acabou de ser dita agora".
                conversa_nova = aguardando_wakeword and self.wakeword is not None
                text = self._ouvir_turno(aguardando_wakeword)
                if not text.strip():
                    # Silêncio dentro da janela de conversa contínua --
                    # acabou a "graça" de pular a palavra de ativação,
                    # volta a exigi-la no próximo turno. Silêncio
                    # enquanto JÁ aguardava a wakeword não muda nada
                    # (já era o estado).
                    aguardando_wakeword = True
                    continue
                print(f"Você disse: {text}")

                if not aguardando_wakeword and _FRASES_ENCERRAR_CONVERSA.match(text.strip()):
                    # "só isso, obrigado" no meio da conversa contínua --
                    # encerra na hora em vez de esperar a janela expirar
                    # sozinha por silêncio.
                    self.tts.speak("De nada.")
                    aguardando_wakeword = True
                    turns += 1
                    continue

                resposta = self.jarvis.process(text)
                saudacao = self._saudacao_por_rosto() if conversa_nova else ""
                resposta_falada = saudacao + resposta
                print(f"Ultron: {resposta_falada}")
                interrompido = self._falar_com_interrupcao(resposta_falada)
                turns += 1

                if interrompido:
                    # Você começou a falar por cima -- o próximo turno
                    # já ouve direto o que você quis dizer, sem exigir
                    # a palavra de ativação (mesmo sem conversa
                    # contínua ligada: você acabou de interromper, é
                    # óbvio que quer falar de novo agora).
                    print("[voz] interrompido -- ouvindo o que você quer dizer...")
                    aguardando_wakeword = False
                else:
                    # Depois de responder, se a conversa contínua estiver
                    # ligada, o PRÓXIMO turno não exige a palavra de
                    # ativação -- só volta a exigir se esse próximo turno
                    # vier em silêncio (ver acima).
                    aguardando_wakeword = not self._em_janela_de_conversa()
            except KeyboardInterrupt:
                print("Encerrando modo voz.")
                break
            except Exception as e:
                log.warning("erro no loop de voz: %s", e)
                print(f"[voz] erro: {e}")
                aguardando_wakeword = True
                # Pequena pausa antes de tentar de novo -- sem isso, um
                # erro que se repete a cada turno (ex.: configuração
                # quebrada) giraria o loop o mais rápido possível,
                # consumindo CPU à toa e spammando o mesmo erro.
                import time
                time.sleep(1.5)
