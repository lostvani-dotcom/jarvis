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
"""

import re

from config.settings import get_settings
from logs.logger import get_logger
from voz.stt import SpeechToText
from voz.tts import TextToSpeech
from voz.wakeword import WakeWordDetector

log = get_logger("voz")

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
                print(f"Ultron: {resposta}")
                self.tts.speak(resposta)
                turns += 1

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
