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
"""

from config.settings import get_settings
from logs.logger import get_logger
from voz.stt import SpeechToText
from voz.tts import TextToSpeech
from voz.wakeword import WakeWordDetector

log = get_logger("voz")


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

        self.jarvis = jarvis
        self.stt = SpeechToText(language=language)
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

    def run(self, max_turns: int = None):
        if not self.available():
            raise RuntimeError(
                "Voz indisponível: instale as dependências de voz "
                "(ver requirements-voz.txt) e verifique o microfone."
            )

        modo = f'com palavra de ativação "{self.wakeword.keyword}"' if self.wakeword else "sem palavra de ativação"
        print(f"Ultron (modo voz, {modo}) pronto. Fale normalmente. Ctrl+C para sair.")
        turns = 0
        while max_turns is None or turns < max_turns:
            try:
                text = self._ouvir_comando()
                if not text.strip():
                    continue
                print(f"Você disse: {text}")

                resposta = self.jarvis.process(text)
                print(f"Ultron: {resposta}")
                self.tts.speak(resposta)
                turns += 1
            except KeyboardInterrupt:
                print("Encerrando modo voz.")
                break
            except Exception as e:
                log.warning("erro no loop de voz: %s", e)
                print(f"[voz] erro: {e}")
                # Pequena pausa antes de tentar de novo -- sem isso, um
                # erro que se repete a cada turno (ex.: configuração
                # quebrada) giraria o loop o mais rápido possível,
                # consumindo CPU à toa e spammando o mesmo erro.
                import time
                time.sleep(1.5)
