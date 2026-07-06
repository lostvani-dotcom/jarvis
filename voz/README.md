# voz/ — Reconhecimento e síntese de voz

100% opcional — sem as dependências abaixo instaladas, `voz.status()`
reporta o que falta e o Jarvis continua funcionando normalmente por
texto.

## Módulos

- `stt.py` — fala → texto. Ordem de preferência: `vosk` (offline) →
  `faster-whisper` (offline) → `speech_recognition` (usa a API
  gratuita do Google — a única opção aqui que é online; escolhida só
  por último, e isso é reportado no status). `vosk`/`faster-whisper`
  gravam em streaming e **param sozinhos ao detectar silêncio** depois
  de você falar (`voz.silencio_para_parar_segundos`, 1s por padrão),
  em vez de sempre esperar uma duração fixa inteira -- `speech_recognition`
  já fazia isso nativamente. Teto de segurança configurável
  (`voz.duracao_maxima_comando_segundos`, 12s por padrão) evita que uma
  gravação fique presa indefinidamente se o microfone captar ruído
  constante.
  **Redução de ruído** (opcional, `noisereduce`): aplicada no áudio
  gravado antes de transcrever, se a lib estiver instalada -- sem ela,
  transcreve o áudio bruto normalmente (degrada graciosamente).
  **Aviso de qualidade baixa**: `listen_and_transcribe_detalhado()`
  retorna `{"texto", "confiavel", "motivo", "idioma_detectado"}` em vez
  de só o texto -- `confiavel=False` quando o trecho gravado não teve
  fala detectável ou volume baixo demais, com `motivo` explicando por
  quê (em vez de devolver silenciosamente um texto vazio/errado).
  `listen_and_transcribe()` continua existindo do jeito que sempre foi
  (só a string), pra não quebrar quem já chama. **Idioma automático**:
  com `faster-whisper` (o único motor aqui com detecção de idioma de
  verdade embutida), configurar `voz.idioma` como `"auto"` detecta
  sozinho em vez de assumir um idioma fixo -- `vosk` e o fallback
  online continuam exigindo um idioma configurado (cada modelo do vosk
  já É de um idioma específico).
- `tts.py` — texto → fala, via `pyttsx3` (offline, usa o motor de voz
  do próprio sistema operacional — SAPI5 no Windows). Modo
  `robotic=True` (config `personalidade.voz_robotica`, ligado por
  padrão): no Windows, fala via SAPI5 direto (`win32com`) usando as
  tags de prosódia XML nativas da API (`<pitch>`/`<rate>`) pra deixar
  o tom mais grave e mecânico -- recurso padrão do Windows, não é
  clonagem de nenhuma voz de terceiros. Tom configurável
  (`personalidade.tom_voz_robotica`, -9 por padrão, escala -10 a 10) e
  também prefere uma voz MASCULINA entre as instaladas no mesmo idioma
  (`_escolher_voz()`, via `GetAttribute("Gender")` do SAPI5, com
  fallback silencioso se o driver da voz não expuser esse atributo) --
  tom grave numa voz já grave de base soa mais parecido com uma IA
  "vilanesca" do que o mesmo tom aplicado a uma voz aguda. Se não
  houver voz masculina instalada no idioma pedido, usa a que houver.
  Sem `pyttsx3` instalado mas com SAPI5 disponível, cai pra fala normal
  via SAPI (sem a prosódia) em vez de simplesmente falhar.
  **Efeito "Ultron" (processamento de áudio)**, config
  `personalidade.efeito_ultron` (ligado por padrão) + `intensidade_ultron`
  (0..1, 0.7 por padrão): em vez de tocar a fala direto, o Jarvis
  renderiza num WAV (SAPI `SpFileStream`) e pós-processa o áudio com
  uma cadeia de efeitos que dá o caráter grave/em-camadas/metálico de
  uma IA vilanesca -- camada detunada (o "coro de vozes"/mais-que-humano),
  ring-modulation sutil (borda metálica sem virar Dalek), soft-clip
  (peso/ameaça) e um reverb curto (espaço frio de servidor) -- depois
  toca via `winsound`. **Isto NÃO é clonagem da voz de ninguém**: é a
  MESMA voz do sistema com efeitos por cima, no ESTILO de uma IA
  grave/ameaçadora -- não reproduz a identidade vocal de nenhuma pessoa
  real ou personagem específico. Requer `numpy` + SAPI (Windows); sem
  eles, cai pra prosódia XML simples (só `<pitch>`), e qualquer falha
  no processamento também cai pra esse fallback -- nunca fica mudo.
- `wakeword.py` — ativação por palavra-chave ("Jarvis"). Usa
  `pvporcupine` (processa o áudio em tempo real, sem transcrever nada,
  baixíssima latência) SE instalado E com uma chave de acesso
  configurada (`voz.picovoice_access_key`, grátis em
  console.picovoice.ai); senão cai para transcrever janelas curtas de
  áudio e procurar a palavra no texto. `listen_for_command()` entende
  tanto "jarvis, comando" numa respiração só (fallback via STT) quanto
  "jarvis" sozinho seguido do comando depois (ambos os backends).
  **Múltiplas palavras de ativação**: `voz.palavras_chave` (lista,
  além de `palavra_chave` singular) aceita mais de uma, ex.
  `["jarvis", "ark"]` -- qualquer uma delas ativa. No Porcupine é
  suporte nativo; no fallback via STT, verifica se qualquer uma
  aparece no texto transcrito. Limitação: o Porcupine só reconhece
  palavras da sua lista pré-treinada (ex. "jarvis", "computer",
  "alexa"...) -- uma palavra fora dessa lista faz o Porcupine falhar
  pro conjunto inteiro, e cai pro fallback via STT (que aceita
  qualquer palavra, sem essa limitação).
- `loop.py` — `VoiceLoop`: ouvir (com ou sem palavra de ativação,
  conforme `voz.ativar_wakeword`) → transcrever → `jarvis.process()` →
  falar. É o que `python main.py --voz` usa em vez do loop de texto.

**Sem `pvporcupine` de verdade funcional antes desta correção**: se a
lib estivesse instalada mas sem chave de acesso configurada, o modo de
voz quebrava (`NotImplementedError`) inteiro, porque o backend nunca
tinha sido implementado de fato -- só detectado. Agora `backend()` só
escolhe Porcupine com uma chave configurada, e o backend em si foi
implementado (stream de áudio via `sounddevice` + `porcupine.process()`).

## Instalação

```bash
pip install -r requirements-voz.txt
```

## Configuração (`config.json` → `voz`)

| Chave | Efeito |
|---|---|
| `ativar_wakeword` | exige dizer a palavra-chave antes de cada comando (ligado por padrão) |
| `palavra_chave` | palavra de ativação (padrão `"jarvis"`) |
| `palavras_chave` | lista de palavras de ativação adicionais, ex. `["ark", "computador"]` -- qualquer uma delas ativa, somada a `palavra_chave` (vazia por padrão) |
| `idioma` | idioma do reconhecimento (`pt-BR`, `en-US`, ...) |
| `motor_stt` / `motor_tts` | forçar um motor específico, ou `"auto"` |
| `picovoice_access_key` | chave grátis do Picovoice pra wake word de baixa latência (opcional -- vazio usa o fallback via STT) |
| `silencio_para_parar_segundos` | quanto silêncio depois de falar até a gravação parar sozinha (padrão 1.0) |
| `duracao_maxima_comando_segundos` | teto de segurança pra gravação de um comando (padrão 12.0) |
| `velocidade_fala` | velocidade da síntese de voz, em "palavras por minuto" estilo pyttsx3 (padrão 205 -- mais rápido que o default comum, ~175-200) |

Velocidade ajustável em tempo real por chat/voz, sem editar o config:
"fala mais rápido" / "fala mais devagar" / "velocidade normal da fala"
(`plugins/system_control.py`) -- some ~25 por vez, com piso 120 e teto
350 pra nunca virar ruído ininteligível nem ficar arrastado demais.

E em `config.json` → `personalidade`: `voz_robotica` (bool, ligado por
padrão) liga o efeito de tom mais grave/mecânico descrito acima.

## Uso

```bash
python main.py --voz
```

```python
from voz import SpeechToText, TextToSpeech

stt = SpeechToText(language="pt-BR")
stt.available()             # True se algum motor + microfone estão prontos
texto = stt.listen_and_transcribe(duration_seconds=5)

resultado = stt.listen_and_transcribe_detalhado(duration_seconds=5)
# {"texto": "...", "confiavel": True, "motivo": None, "idioma_detectado": None}

tts = TextToSpeech()
tts.speak("Olá, sou o Jarvis.")
```
