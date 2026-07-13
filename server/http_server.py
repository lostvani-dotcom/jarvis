"""
server/http_server.py
========================
Servidor HTTP local do Ultron -- 100% biblioteca padrão
(`http.server`), sem dependência nova. Deixa o app do celular
(app_android/) conversar com a MESMA instância de Ultron que já está
rodando na GUI ou no terminal (memória/histórico compartilhados, não é
uma sessão separada).

Rede local (LAN) só: escuta em todas as interfaces (`0.0.0.0`) pra o
celular alcançar o IP do PC na mesma Wi-Fi -- igual ao ADB sem fio
(dispositivos/adb.py), isso NUNCA mexe em configuração de
roteador/port-forwarding, então continua fora do alcance da internet a
menos que o usuário exponha isso manualmente (não recomendado).

Autenticação: todo endpoint (exceto `/`, `/status`, `/app.apk` e
`/qr.png`, que são só a página de instalação) exige o header
`Authorization: Bearer <token>`. O token é gerado uma vez e persistido
em `config.json` -> `servidor.token` (`get_or_create_token()`). O app
do celular recebe esse token automaticamente ao descobrir o Ultron na
rede (server/discovery.py) -- decisão consciente de UX sobre segurança
(ver docstring de discovery.py): o perímetro de confiança é "estar na
Wi-Fi de casa", não mais "digitar o token à mão".

Endpoints:
    GET  /                           -> página HTML de instalação (QR code + botão de
        download) -- abra http://<ip-do-pc>:8765/ no navegador (do PC ou do celular)
    GET  /status                    -> {"ok": true, "nome": "Ultron"} (sem auth)
    GET  /app.apk                   -> baixa o APK do app companion (sem auth --
        é só o instalador, o token continua protegendo os endpoints de verdade)
    GET  /qr.png                    -> QR code apontando pra /app.apk (requer `qrcode`
        instalado; sem isso, a página de instalação cai pro link direto)
    POST /chat    {"text": str}     -> {"resposta": str}
    POST /notify  {"pacote", "titulo", "texto"} -> {"ok": true}
        (o app manda notificações capturadas nativamente -- ver
        automacao/notification_inbox.py)
    GET  /poll                      -> {"mensagens": [...]}
        (long-poll simples: lembretes/comentários que o Ultron quis
        avisar por conta própria -- ver automacao/notify.py, que
        registra este servidor como mais um notifier)
    GET  /device/commands           -> {"comando": {...} | null}
        (o app pergunta, num loop curto (agora em segundo plano, via
        NotifyListenerService), se o Ultron pediu algo -- bateria,
        abrir app, app em primeiro plano -- ver
        automacao/phone_commands.py)
    POST /device/result {"id", "resultado"} -> {"ok": true}
        (o app devolve o resultado do comando que executou)
    GET  /app/version                -> {"versionCode": int, "versionName": str} (sem auth
        -- o app compara com a própria versão instalada e se oferece pra
        se autoatualizar, baixando /app.apk e disparando a instalação)
    GET  /loja/catalogo               -> {"apps": [...]} (sem auth -- ver
        server/loja_catalogo.py; usado pelo app "Loja Ultron", app_android/loja/)
    GET  /loja/apps/<arquivo>          -> baixa um .apk do catálogo da loja (sem
        auth, mesmo motivo de /app.apk -- só nomes já cadastrados no catálogo)
    GET  /loja                        -> redireciona pra /site/loja.html (atalho)
    GET  /dossie                       -> redireciona pra /site/index.html (atalho)
    GET  /site/<caminho>                -> serve o site estático (site/, HTML/CSS/TS
        compilado) direto deste servidor -- mesmos arquivos do repositório, só que
        alcançáveis pelo celular também, sem precisar abrir o arquivo local no PC.
    POST /visao/identificar {corpo: JPEG cru} -> {"rostos": [{"nome","confianca"}, ...]}
        (com auth -- reconhecimento facial via foto, ver visao/faces.py. Usado pelo
        Companion pra "quem é essa pessoa" com a câmera do celular)
    POST /voz/amostra {corpo: áudio cru, Content-Type indica formato} -> {"ok": true}
        (com auth -- salva a amostra de referência pra clonagem de voz vinda do
        celular, ver voz/clonagem.py:salvar_amostra_upload)
    POST /redcore/historico {"url","titulo","conteudo","user_id"} -> {"ok": true, "id": int}
        (com auth -- sincronização OPT-IN do histórico do RedCore Mobile pro mesmo
        histórico do RedCore do PC, ver automacao/redcore_historico.py)
    GET  /backup/completo             -> baixa um .zip com banco de dados + config +
        chave de criptografia (com auth -- é o backup mais sensível que existe, nunca
        sem token). Ver seguranca/backup.py e seguranca/restaurar_backup.py.
"""

import json
import mimetypes
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from automacao.notification_inbox import registrar as registrar_notificacao
from automacao.phone_commands import pegar_comando_pendente, submeter_resultado
from config.settings import get_settings
from logs.logger import get_logger

log = get_logger("server")

_pending_lock = threading.Lock()
_pending_messages = []

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APK_PATH = os.path.join(_BASE_DIR, "app_android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")
_APP_GRADLE_PATH = os.path.join(_BASE_DIR, "app_android", "app", "build.gradle.kts")
_SITE_DIR = os.path.join(_BASE_DIR, "site")


def _resolver_arquivo_site(caminho_relativo: str):
    """Resolve um caminho pedido em GET /site/<caminho> com segurança
    -- normaliza e confere que o resultado continua DENTRO de site/,
    senão um pedido tipo /site/../config/config.json poderia vazar
    qualquer arquivo do projeto. Retorna None se o caminho escapa de
    site/ ou o arquivo não existe."""
    limpo = caminho_relativo.split("?")[0].lstrip("/")
    if not limpo:
        limpo = "index.html"
    alvo = os.path.normpath(os.path.join(_SITE_DIR, limpo))
    raiz = os.path.abspath(_SITE_DIR)
    if alvo != raiz and not alvo.startswith(raiz + os.sep):
        return None
    return alvo if os.path.isfile(alvo) else None


def get_or_create_token() -> str:
    settings = get_settings()
    token = settings.get("servidor.token", "")
    if not token:
        token = secrets.token_urlsafe(24)
        settings.set("servidor.token", token)
        settings.save()
    return token


def _app_version() -> dict:
    """Lê versionCode/versionName direto de app_android/app/build.gradle.kts
    -- sem precisar do Android SDK/aapt instalado só pra isso, é
    suficiente parsear o texto do arquivo, já que o formato é
    previsível (nós mesmos escrevemos)."""
    try:
        with open(_APP_GRADLE_PATH, "r", encoding="utf-8") as f:
            texto = f.read()
        m_code = re.search(r"versionCode\s*=\s*(\d+)", texto)
        m_name = re.search(r'versionName\s*=\s*"([^"]*)"', texto)
        return {
            "versionCode": int(m_code.group(1)) if m_code else 0,
            "versionName": m_name.group(1) if m_name else "?",
        }
    except Exception as e:
        log.warning("falha ao ler versão do app_android: %s", e)
        return {"versionCode": 0, "versionName": "?"}


def _ia_config_para_app(jarvis) -> dict:
    """Configuração pro app do celular falar DIRETO com o provedor de
    IA (formato OpenAI chat/completions) quando o PC estiver desligado.
    Só provedores desse formato entram (NVIDIA, OpenAI, Mistral, etc. --
    tudo que ia/providers/openai_compatible.py cobre); um modelo local
    (Ollama/LM Studio) não adianta pro celular fora desta máquina, então
    provedores 'local' são pulados. Vazio ({"disponivel": False}) quando
    não há provedor remoto configurado."""
    try:
        from core.personality import build_system_prompt
        from config.settings import get_settings
        estilo = get_settings().get("personalidade.estilo", "padrao")
        prompt = build_system_prompt(estilo=estilo)
        if jarvis is None or jarvis.ia_manager is None:
            return {"disponivel": False}
        for p in jarvis.ia_manager.available_providers():
            base_url = getattr(p, "base_url", "")
            api_key = getattr(p, "api_key", "")
            if not base_url or not api_key or getattr(p, "kind", "remoto") == "local":
                continue
            return {
                "disponivel": True,
                "base_url": base_url,
                "api_key": api_key,
                "modelo": getattr(p, "model", ""),
                "auth_header": getattr(p, "auth_header", "Authorization"),
                "system_prompt": prompt,
            }
        return {"disponivel": False}
    except Exception as e:
        log.warning("falha ao montar config de IA pro app: %s", e)
        return {"disponivel": False}


def queue_message_for_phone(titulo: str, mensagem: str):
    """Registrado como notifier em automacao/notify.py (ver
    start_server()): qualquer coisa que o Ultron avise por conta
    própria (lembrete, comentário de observação) também fica
    disponível aqui pro celular buscar via GET /poll."""
    with _pending_lock:
        _pending_messages.append({"titulo": titulo, "mensagem": mensagem, "quando": time.time()})
        del _pending_messages[:-100]


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_apk(self):
        if not os.path.isfile(_APK_PATH):
            self._send_json(
                404,
                {"erro": "APK não encontrado -- compile com app_android/gradlew.bat assembleDebug"},
            )
            return
        with open(_APK_PATH, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Disposition", 'attachment; filename="jarvis.apk"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_loja_apk(self, arquivo: str):
        # Sem auth (mesmo padrão de /app.apk -- é só o instalador). O
        # nome do arquivo só é aceito se bater com uma entrada JÁ
        # cadastrada no catálogo (loja_catalogo.caminho_apk), então uma
        # URL tipo /loja/apps/../../config/config.json nunca resolve
        # pra nada -- sem isso, o path viria direto da URL do cliente.
        from server import loja_catalogo
        caminho = loja_catalogo.caminho_apk(arquivo)
        if not caminho:
            self._send_json(404, {"erro": f"'{arquivo}' não está no catálogo da loja"})
            return
        with open(caminho, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Disposition", f'attachment; filename="{arquivo}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _apk_url(self) -> str:
        host_header = self.headers.get("Host", "localhost:8765")
        return f"http://{host_header}/app.apk"

    def _send_landing_page(self):
        apk_url = self._apk_url()
        html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ultron</title>
<style>
  body {{ background:#000; color:#e5e7eb; font-family:-apple-system,"Segoe UI",sans-serif;
          text-align:center; padding:40px 20px; margin:0; }}
  h1 {{ color:#4fd1ff; letter-spacing:6px; font-size:28px; }}
  p {{ color:#9ca3af; max-width:420px; margin:16px auto; line-height:1.5; }}
  .qr {{ margin-top:24px; border-radius:12px; background:#fff; padding:12px; max-width:220px; }}
  .btn {{ display:inline-block; margin-top:24px; padding:14px 28px; background:#0ea5b5;
          color:#000; font-weight:bold; text-decoration:none; border-radius:8px; }}
  code {{ color:#4fd1ff; }}
</style>
</head>
<body>
  <h1>JARVIS</h1>
  <p>Escaneie o QR code com a câmera do celular pra baixar o app, ou toque no botão abaixo.</p>
  <img class="qr" src="/qr.png" width="220" height="220" alt="QR code para baixar o app"
       onerror="this.style.display='none'">
  <div><a class="btn" href="/app.apk">Baixar APK</a></div>
  <p>Depois de instalado, o app busca o Ultron na rede sozinho. O token de pareamento fica
  em <code>config/config.json</code> &rarr; <code>servidor.token</code>.</p>
</body>
</html>"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_qr(self):
        try:
            import io
            import qrcode
            img = qrcode.make(self._apk_url())
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            body = buf.getvalue()
        except Exception as e:
            self._send_json(404, {"erro": f"qrcode indisponível ({e}) -- use o link direto /app.apk"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_site_file(self, caminho_relativo: str):
        # Sem auth (é conteúdo público explicativo, ver docstring do
        # módulo -- mesmo perímetro de confiança de /app.apk).
        alvo = _resolver_arquivo_site(caminho_relativo)
        if alvo is None:
            self._send_json(404, {"erro": "arquivo não encontrado no site"})
            return
        tipo, _ = mimetypes.guess_type(alvo)
        with open(alvo, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tipo or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, destino: str):
        self.send_response(302)
        self.send_header("Location", destino)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _identificar_rosto(self):
        """POST /visao/identificar -- corpo é uma foto JPEG crua
        (não JSON, por isso tratado ANTES de _read_json() em do_POST).
        Usado pelo Companion pra "quem é essa pessoa" via câmera do
        celular, reaproveitando o MESMO reconhecedor LBPH do PC (ver
        plugins/reconhecimento_facial.py -- os rostos cadastrados são
        os mesmos, não importa se cadastrados pela câmera do PC ou
        identificados a partir de uma foto do celular)."""
        corpo = self._read_body()
        if not corpo:
            self._send_json(400, {"erro": "corpo vazio -- envie a foto em JPEG"})
            return
        try:
            import numpy as np
            import cv2
            from visao.faces import get_recognizer

            array = np.frombuffer(corpo, dtype=np.uint8)
            frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
            if frame is None:
                self._send_json(400, {"erro": "não consegui decodificar a imagem (envie um JPEG válido)"})
                return
            recognizer = get_recognizer()
            if not recognizer.available():
                self._send_json(503, {"erro": "reconhecimento facial indisponível no servidor (falta opencv-contrib-python)"})
                return
            resultados = recognizer.identify(frame)
            rostos = [{"nome": r["nome"], "confianca": r["confianca"]} for r in resultados]
            self._send_json(200, {"rostos": rostos})
        except Exception as e:
            log.warning("falha ao identificar rosto via upload: %s", e)
            self._send_json(500, {"erro": str(e)})

    def _receber_amostra_voz(self):
        """POST /voz/amostra -- corpo é o áudio cru gravado pelo
        celular (não JSON). `Content-Type` indica o formato pra saber
        que extensão salvar (ver voz/clonagem.py:salvar_amostra_upload
        -- o XTTS lê o áudio via ffmpeg/librosa na hora de sintetizar,
        não precisa ser WAV)."""
        corpo = self._read_body()
        if not corpo:
            self._send_json(400, {"erro": "corpo vazio -- envie o áudio gravado"})
            return
        from voz import clonagem
        if not clonagem.disponivel():
            self._send_json(503, {"erro": "clonagem de voz indisponível no servidor (falta coqui-tts)"})
            return
        tipo = self.headers.get("Content-Type", "audio/mp4")
        extensao = "wav" if "wav" in tipo else "m4a"
        resultado = clonagem.salvar_amostra_upload(corpo, extensao)
        if not resultado["sucesso"]:
            self._send_json(400, resultado)
            return
        self._send_json(200, {"ok": True})

    def _enviar_backup_completo(self):
        try:
            from seguranca.backup import criar_pacote_completo
            caminho = criar_pacote_completo()
        except Exception as e:
            self._send_json(500, {"erro": f"falha ao gerar backup: {e}"})
            return
        with open(caminho, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(caminho)}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _autorizado(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {self.server.token}"

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/":
            self._send_landing_page()
            return

        if self.path == "/status":
            self._send_json(200, {"ok": True, "nome": "Ultron"})
            return

        if self.path == "/app.apk":
            self._send_apk()
            return

        if self.path == "/qr.png":
            self._send_qr()
            return

        if self.path == "/app/version":
            self._send_json(200, _app_version())
            return

        if self.path == "/loja/catalogo":
            # Sem auth -- mesmo padrão de /app.apk e /app/version: é só
            # metadado de instalador, não dado do usuário.
            from server import loja_catalogo
            self._send_json(200, {"apps": loja_catalogo.listar()})
            return

        if self.path.startswith("/loja/apps/"):
            self._send_loja_apk(self.path[len("/loja/apps/"):])
            return

        if self.path == "/loja":
            self._send_redirect("/site/loja.html")
            return

        if self.path == "/dossie":
            self._send_redirect("/site/index.html")
            return

        if self.path.startswith("/site/") or self.path == "/site":
            self._send_site_file(self.path[len("/site/"):] if self.path != "/site" else "")
            return

        if self.path == "/backup/completo":
            # Com auth SEMPRE -- é o backup mais sensível que existe
            # (inclui a chave de criptografia), diferente de /app.apk
            # e afins, que são só instaladores públicos.
            if not self._autorizado():
                self._send_json(401, {"erro": "token inválido"})
                return
            self._enviar_backup_completo()
            return

        if self.path.startswith("/poll"):
            if not self._autorizado():
                self._send_json(401, {"erro": "token inválido"})
                return
            with _pending_lock:
                mensagens = list(_pending_messages)
                _pending_messages.clear()
            self._send_json(200, {"mensagens": mensagens})
            return

        if self.path == "/device/commands":
            if not self._autorizado():
                self._send_json(401, {"erro": "token inválido"})
                return
            self._send_json(200, {"comando": pegar_comando_pendente()})
            return

        if self.path == "/ia/config":
            # Entrega ao app pareado a configuração do provedor de IA
            # (URL/chave/modelo) + o prompt de personalidade, pra ele
            # conversar DIRETO com a nuvem quando este PC estiver
            # desligado. Exige o token (mesmo perímetro de confiança do
            # /chat: quem tem o token já pode usar a IA à vontade por
            # aqui de qualquer forma -- isso não expõe nada novo, só
            # remove a dependência do PC estar de pé).
            if not self._autorizado():
                self._send_json(401, {"erro": "token inválido"})
                return
            self._send_json(200, _ia_config_para_app(self.server.jarvis_instance))
            return

        self._send_json(404, {"erro": "não encontrado"})

    def do_POST(self):
        if not self._autorizado():
            self._send_json(401, {"erro": "token inválido"})
            return

        # Corpo BINÁRIO (foto/áudio cru, não JSON) -- tratado ANTES de
        # _read_json() de propósito: _read_json() consome o corpo
        # inteiro do rfile tentando json.loads(), e o stream HTTP só
        # pode ser lido uma vez. Rotear esses dois aqui evita esse
        # conflito com os endpoints JSON abaixo.
        if self.path == "/visao/identificar":
            self._identificar_rosto()
            return

        if self.path == "/voz/amostra":
            self._receber_amostra_voz()
            return

        dados = self._read_json()

        if self.path == "/redcore/historico":
            # Sincronização OPT-IN do histórico do RedCore Mobile --
            # mesma tabela/formato do RedCore do PC (automacao/
            # redcore_historico.py), então "o que eu vi hoje" já
            # inclui o que você navegou pelo celular também.
            url = (dados.get("url") or "").strip()
            if not url:
                self._send_json(400, {"erro": "campo 'url' vazio"})
                return
            user_id = dados.get("user_id") or "default_user"
            titulo = dados.get("titulo", "")
            conteudo = dados.get("conteudo", "")
            try:
                from automacao import redcore_historico
                visita_id = redcore_historico.registrar_visita(user_id, url, titulo, conteudo)
                self._send_json(200, {"ok": True, "id": visita_id})
            except Exception as e:
                log.warning("falha ao sincronizar histórico do RedCore Mobile: %s", e)
                self._send_json(500, {"erro": str(e)})
            return

        if self.path == "/chat":
            texto = (dados.get("text") or "").strip()
            if not texto:
                self._send_json(400, {"erro": "campo 'text' vazio"})
                return
            try:
                resposta = self.server.jarvis_instance.process(texto)
            except Exception as e:
                log.warning("erro processando /chat: %s", e)
                self._send_json(500, {"erro": str(e)})
                return
            self._send_json(200, {"resposta": resposta})
            return

        if self.path == "/notify":
            registrar_notificacao(
                dados.get("pacote", ""), dados.get("titulo", ""), dados.get("texto", ""),
            )
            self._send_json(200, {"ok": True})
            return

        if self.path == "/device/result":
            ok = submeter_resultado(dados.get("id", ""), dados.get("resultado", {}))
            self._send_json(200, {"ok": ok})
            return

        self._send_json(404, {"erro": "não encontrado"})


class JarvisHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, jarvis, host: str, port: int, token: str):
        super().__init__((host, port), _Handler)
        self.jarvis_instance = jarvis
        self.token = token


def start_server(jarvis, host: str = "0.0.0.0", port: int = None):
    """Sobe o servidor numa thread de fundo (daemon) e registra
    `queue_message_for_phone` como notifier genérico (automacao/notify.py),
    então lembretes/observação também chegam no celular via /poll.
    Retorna (httpd, token) -- o app do celular recebe esse mesmo token
    automaticamente via descoberta (server/discovery.py), sem precisar
    digitar nada."""
    settings = get_settings()
    port = port or int(settings.get("servidor.porta", 8765))
    token = get_or_create_token()

    httpd = JarvisHTTPServer(jarvis, host, port, token)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    try:
        from automacao.notify import add_notifier
        add_notifier(lambda titulo, mensagem: queue_message_for_phone(titulo, mensagem))
    except Exception as e:
        log.warning("falha ao registrar notifier do servidor: %s", e)

    try:
        from server.discovery import start_discovery
        start_discovery(port, token)
    except Exception as e:
        log.warning("falha ao iniciar descoberta automática (app precisará de IP/token manual): %s", e)

    log.info("Servidor Ultron em http://%s:%s (token exigido, exceto /status)", host, port)
    return httpd, token
