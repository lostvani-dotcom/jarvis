# app_android/ — Apps Android do ecossistema Ultron

Projeto Gradle com TRÊS apps nativos (Kotlin), um módulo cada, todos
conectando no Ultron rodando no PC (via [`server/`](../server/README.md),
o servidor HTTP local) pela mesma rede Wi-Fi -- sem cabo, sem ADB, sem
expor nada na internet. Baixe/instale todos pela [Loja Ultron](../site/loja.html)
(`.\gradlew.bat assembleDebug` compila os três de uma vez; ou
`:app:assembleDebug` / `:loja:assembleDebug` / `:redcore:assembleDebug`
pra compilar um só):

- **`app/`** (`com.jarvis.companion`, descrito abaixo) -- chat, comandos
  do celular, notificações.
- **`loja/`** (`com.ultron.loja`) -- a própria loja: descobre o Ultron
  na rede, lista o catálogo (`server/loja_catalogo.py`) e instala
  qualquer um dos três apps com um toque.
- **`redcore/`** (`com.ultron.redcore`) -- versão leve do navegador
  RedCore do PC (`gui/redcore.py`) pro celular: abas, barra de
  endereço com busca embutida, mesmo visual vermelho/preto.

## App Companion (`app/`)

Funções:
1. **Chat com o Jarvis** direto do celular (tela principal).
2. **Encaminha notificações automaticamente** (Instagram, WhatsApp,
   Messenger, Telegram) pro Jarvis, via `NotificationListenerService`
   nativo do Android -- muito mais confiável que o fallback por ADB
   (`dispositivos/adb.py:list_notifications()`, baseado em
   `dumpsys notification`). Usado por `plugins/instagram.py` pra
   sugerir respostas.
3. **Responde aos comandos do Jarvis com o app FECHADO** (bateria,
   abrir app, app em primeiro plano, volume, lanterna, achar o
   celular, armazenamento -- ver `plugins/device_control.py`): o
   mesmo `NotifyListenerService` que encaminha notificações também
   faz polling curto em segundo plano, então "vê a bateria do
   celular" funciona sem precisar deixar a tela do app aberta --
   só precisa do acesso a notificações concedido (item abaixo).
4. **Se autoatualiza sozinho**: ao abrir (ou reconectar), o app
   compara sua versão com a que o PC está servindo (`GET
   /app/version`) e, se tiver uma mais nova, baixa e dispara a
   instalação sozinho -- sem precisar escanear o QR code de novo
   toda vez que uma mudança for feita no app.
5. **Fala com o Jarvis por voz** (botão 🎤 ao lado do campo de
   mensagem): usa `SpeechRecognizer`/`TextToSpeech` nativos do Android
   (mesmo motor do teclado/assistente do sistema -- zero dependência
   nova). Pede a permissão de microfone só na primeira vez que você
   toca no botão, e retoma a escuta sozinho assim que concedida. A
   resposta do Jarvis é falada em voz alta automaticamente quando a
   pergunta foi feita por voz (digitado continua só em texto). Entrada
   por voz sempre vira uma mensagem NATURAL (nunca prefixada com "/"),
   mesma convenção do modo de comando direto (ver README principal,
   seção "Modo de comando direto").

## Setup do ambiente de build (uma vez só)

O projeto foi criado e compilado usando ferramentas baixadas em
`tools/` (fora do controle de versão -- ver `.gitignore`), sem
depender do Android Studio instalado:

- **JDK 17** (Eclipse Temurin) -- exigido pelo Android Gradle Plugin 8.x.
- **Android SDK command-line tools** (`platform-tools`,
  `platforms;android-34`, `build-tools;34.0.0`).
- **Gradle 8.7** -- só usado pra gerar o wrapper (`gradlew`/`gradlew.bat`)
  deste projeto; depois disso, o wrapper se vira sozinho.

Se for compilar numa máquina nova, mais simples: instale o **Android
Studio** normalmente (ele já traz JDK + SDK + Gradle configurados) e
abra a pasta `app_android/` como projeto -- os arquivos aqui são um
projeto Gradle padrão, sem nada específico do setup manual.

Pra compilar via linha de comando (o jeito usado aqui), com o JDK 17 e
o SDK já instalados:

```powershell
$env:JAVA_HOME = "<caminho para o JDK 17>"
cd app_android
.\gradlew.bat assembleDebug
```

O `local.properties` (não versionado) precisa apontar `sdk.dir` pro
Android SDK:

```
sdk.dir=C:\\caminho\\para\\android-sdk
```

O APK de debug sai em
`app\build\outputs\apk\debug\app-debug.apk`.

## Instalar no celular

**Sem cabo** (mais fácil): com o Jarvis rodando no PC, abra
`http://<IP-do-PC>:8765/` no navegador -- mostra uma página com QR
code (escaneie com a câmera do celular, na mesma Wi-Fi, pra baixar
direto) e um botão "Baixar APK" (se preferir digitar o endereço no
próprio celular). O QR code precisa de `qrcode` instalado
(`pip install qrcode`); sem isso, use o botão/link direto pra
`/app.apk`. Depois de baixar, abra o arquivo e permita "instalar de
fontes desconhecidas" quando o Android pedir.

**Com ADB** (alternativa): `adb install app-debug.apk` com o celular
já conectado (ver [`dispositivos/README.md`](../dispositivos/README.md)
pra conectar por Wi-Fi sem cabo).

Depois, abra o app "Jarvis" no celular.

## Parear com o Jarvis

Totalmente automático: com o Jarvis rodando no PC, abra o app -- ele
já busca sozinho ao abrir (ou toque em "Buscar o Jarvis
automaticamente" a qualquer momento). Encontrando, IP, porta **e
token** vêm juntos e a conexão já fica pronta, sem digitar nada.

Depois, toque em "Notificações" pra abrir a tela do Android de acesso
a notificações, e habilite pro app "Jarvis" -- essa permissão faz
DUAS coisas: encaminha notificações E liga o polling em segundo plano
que responde bateria/abrir app/etc. com o app fechado. Sem ela, nada
disso funciona (é uma permissão que o Android exige conceder
manualmente, nenhum app pode se autoconceder).

Pra "o que está aberto no celular" funcionar, toque também em "Acesso
ao uso" (outra permissão manual, Android exige por privacidade --
apps normais não podem saber o que outros apps estão fazendo sem essa
concessão explícita).

**Se os comandos pararem de responder depois de um tempo** com o app
fechado: alguns fabricantes (Xiaomi, Huawei, Samsung, e outros com
otimização de bateria agressiva) matam serviços em segundo plano
mesmo com a permissão concedida. Se isso acontecer, desative a
otimização de bateria pro app "Jarvis" nas configurações do aparelho
(geralmente em Configurações > Bateria > Otimização de bateria >
Jarvis > Não otimizar).

Se a busca automática não achar nada (ex.: rede que bloqueia
broadcast UDP), preencha IP, porta e token manualmente -- `ipconfig`
no PowerShell mostra o "Endereço IPv4", e o token fica em
`config/config.json` -> `servidor.token`.

### Descoberta automática (como funciona, e a troca de segurança envolvida)

O app manda um broadcast UDP (`JARVIS_DISCOVER`) na porta 8766; o
Jarvis (`server/discovery.py`) responde com IP, porta **e o token de
autenticação**. Isso foi uma decisão consciente pra eliminar a
fricção de copiar um token de 32 caracteres manualmente -- o efeito
colateral é que **qualquer aparelho capaz de mandar esse broadcast na
mesma rede Wi-Fi consegue descobrir e usar o Jarvis**, não só o seu
celular. O perímetro de confiança passa a ser "estar na sua Wi-Fi de
casa", não mais "conhecer o token". Pra uma rede doméstica isso é um
risco baixo; se a rede for compartilhada com gente não confiável,
desligue `modulos.servidor` em `config.json` ou edite
`server/discovery.py` pra tirar o token da resposta.

Depois de pareado, o celular e o PC precisam continuar na mesma rede
Wi-Fi -- não há acesso de fora de casa (ver a discussão de segurança em
[`plugins/instagram.py`](../plugins/instagram.py) sobre por que isso é
intencional).

## Estrutura

```
app_android/
├── app/src/main/
│   ├── AndroidManifest.xml
│   ├── java/com/jarvis/companion/
│   │   ├── MainActivity.kt          # tela de chat + configuração + autoatualização + voz (STT/TTS)
│   │   ├── JarvisClient.kt          # cliente HTTP pro server/
│   │   ├── Discovery.kt             # busca o Jarvis na rede (UDP broadcast)
│   │   ├── NotifyListenerService.kt # notificações + polling de comandos em 2º plano
│   │   ├── DeviceCommands.kt        # executa bateria/volume/lanterna/etc. localmente
│   │   ├── NotificacaoLocal.kt      # mostra aviso do sistema quando o app está fechado
│   │   └── Prefs.kt                 # IP/porta/token (SharedPreferences)
│   └── res/                          # layout, tema (preto/ciano, igual à GUI), ícone
├── gradlew / gradlew.bat
└── local.properties (não versionado -- caminho do Android SDK)
```

## Limitações honestas

- Testado só até "compila e produz um APK válido" (`aapt dump
  badging` confirma pacote, permissões e activity corretos) e um
  ciclo de comando/resposta simulado do lado do PC -- não há como
  instalar/rodar num aparelho real ou emulador neste ambiente de
  desenvolvimento. Teste no seu celular de verdade antes de confiar
  100%.
- `NotifyListenerService` só encaminha notificações de apps
  conhecidos (Instagram, WhatsApp, Messenger, Telegram) -- adicione
  mais pacotes em `pacotesRelevantes` se quiser cobrir outros apps.
- Polling em segundo plano depende do Android manter o
  `NotifyListenerService` vivo -- normalmente confiável, mas alguns
  fabricantes matam serviços agressivamente (ver seção acima sobre
  otimização de bateria).
- Autoatualização reinstala por cima da versão atual (mesma
  assinatura de debug) -- funciona sem perder dados do app (host/
  porta/token ficam salvos), mas ainda pede a confirmação padrão do
  Android pra instalar um APK (não é silenciosa, o sistema sempre
  mostra essa tela por segurança).
- Sem HTTPS (ver nota no `AndroidManifest.xml`) -- aceitável pra
  tráfego só dentro da rede Wi-Fi de casa, mesmo modelo de confiança
  do ADB sem fio.
- Reconhecimento/síntese de voz usam o motor padrão do aparelho
  (`SpeechRecognizer`/`TextToSpeech` do Android) -- qualidade e se
  funciona 100% offline dependem do fabricante/versão do Android, não
  do Jarvis. Em muitos aparelhos, o reconhecimento de voz do sistema
  usa os servidores do Google por trás (mesmo sem chamar nenhuma API
  do Jarvis) -- isso é comportamento do próprio Android, não algo que
  o app controla.
