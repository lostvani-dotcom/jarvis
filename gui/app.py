"""
gui/app.py
==========
Interface gráfica do Ultron: fundo preto, o orbe "molécula"
(gui/orb.py) reagindo ao estado da IA, e um chat mostrando as
respostas -- da base de conhecimento, plugins (inclusive abrir
programas, via automacao/apps.py) ou IA externa. Tudo passa pelo mesmo
`Ultron.process()` do modo texto (core/jarvis.py), então qualquer
coisa que funciona no terminal funciona aqui também.

Processar uma mensagem pode envolver uma chamada de rede (provedor de
IA externo) e não pode travar a interface -- por isso roda numa
QThread (_ProcessWorker) enquanto o orbe anima "pensando".

`Ultron(user_id=...)` em si também não é instantâneo -- carrega
memória, plugins, base de conhecimento, detecção de GPU (que importa
`torch`, o maior custo sozinho) e sobe o servidor do app do celular
(server/), e isso pode levar de alguns segundos a mais de 20s
dependendo da máquina. Por isso a janela aparece IMEDIATAMENTE, num
estado "carregando", enquanto `Ultron()` é criado numa QThread
separada (`_UltronLoader`) -- sem isso, a janela inteira ficava
invisível até o carregamento terminar, o que parecia (e na prática
era) "o programa não abre".

Voz (TTS): a GUI é só texto por padrão em outros lugares do projeto
(o modo de voz "de verdade" é `python main.py --voz`, ver voz/loop.py),
mas aqui a GUI TAMBÉM fala as respostas em voz alta (botão "Voz" liga/
desliga) -- usa o mesmo `voz.tts.TextToSpeech` (com o efeito robótico
de `personalidade.voz_robotica`, se ligado). Falas rodam numa fila
processada por um único `_SpeakWorker` persistente: `pyttsx3` não é
seguro pra chamadas concorrentes na mesma engine, então enfileirar
evita sobrepor ou corromper falas quando duas respostas chegam perto
uma da outra (chat + notificação, por exemplo).
"""

import html
import queue
import sys
import time

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import get_settings
from core.jarvis import Jarvis
from core.personality import NOME
from gui.eye import UltronEye
from voz.tts import TextToSpeech


class _NotifyBridge(QObject):
    """Ponte thread-safe entre uma notificação disparada em thread de
    fundo (lembrete, comentário automático -- ambos via
    threading.Timer, ver automacao/tasks.py) e a UI Qt, que só pode ser
    tocada pela thread principal. Sinais Qt emitidos de outra thread
    para um slot na thread principal usam conexão em fila
    automaticamente, então isto é seguro."""
    fired = Signal(str, str)


class _ProcessWorker(QThread):
    done = Signal(str)

    def __init__(self, jarvis: Jarvis, text: str, parent=None):
        super().__init__(parent)
        self._jarvis = jarvis
        self._text = text

    def run(self):
        try:
            resposta = self._jarvis.process(self._text)
        except Exception as e:
            resposta = f"Erro ao processar: {e}"
        self.done.emit(resposta)


class _ListenWorker(QThread):
    """Grava e transcreve UM comando por voz (voz/stt.py) numa thread
    separada -- gravar bloqueia por até alguns segundos, e a UI não
    pode travar durante isso. Usa a mesma detecção de silêncio de
    voz/stt.py:_gravar_ate_silencio (para sozinho ao detectar que você
    parou de falar, sem esperar sempre a duração máxima)."""
    ouviu = Signal(str)
    falhou = Signal(str)

    def run(self):
        try:
            from voz.stt import SpeechToText
            stt = SpeechToText(language="pt-BR")
            if not stt.available():
                self.falhou.emit(
                    "Nenhum motor de voz disponível (instale 'vosk'/'faster-whisper'/"
                    "'SpeechRecognition' + 'sounddevice', ver requirements-voz.txt)."
                )
                return
            texto = stt.listen_and_transcribe(duration_seconds=12.0)
            self.ouviu.emit(texto.strip())
        except Exception as e:
            self.falhou.emit(str(e))


class _SpeakWorker(QThread):
    """Fala uma fila de textos, um de cada vez, numa thread persistente
    -- pyttsx3 não é seguro pra chamadas concorrentes na mesma engine,
    então uma fila com um único worker evita sobrepor falas."""

    def __init__(self, tts: TextToSpeech, parent=None):
        super().__init__(parent)
        self._tts = tts
        self._fila = queue.Queue()
        self._parar = False

    def enqueue(self, texto: str):
        self._fila.put(texto)

    def parar(self):
        self._parar = True
        self._fila.put(None)

    def run(self):
        while not self._parar:
            try:
                texto = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            if texto is None:
                break
            try:
                self._tts.speak(texto)
            except Exception:
                pass


class _JarvisLoader(QThread):
    """Constrói o Ultron(user_id=...) fora da thread principal -- essa
    chamada sozinha pode levar vários segundos (ver nota no topo do
    arquivo), e a janela não pode ficar invisível esse tempo todo."""
    pronto = Signal(object)
    falhou = Signal(str)

    def __init__(self, user_id: str, parent=None):
        super().__init__(parent)
        self.user_id = user_id

    def run(self):
        try:
            jarvis = Jarvis(user_id=self.user_id)
        except Exception as e:
            self.falhou.emit(str(e))
            return
        self.pronto.emit(jarvis)


class MainWindow(QMainWindow):
    def __init__(self, user_id: str):
        super().__init__()
        self.jarvis = None
        self.user_id = user_id
        self._worker = None
        self._speak_worker = None
        self._listen_worker = None
        self._voice_enabled = True
        self._resposta_inicio = time.monotonic()

        self._pensando_timer = QTimer(self)
        self._pensando_timer.setInterval(400)
        self._pensando_timer.timeout.connect(self._animar_pensando)
        self._pensando_dots = 0

        self.setWindowTitle(NOME)
        self.resize(880, 680)
        self._build_ui()
        self._build_tray()
        self._start_loading()

    def closeEvent(self, event):
        if self._speak_worker is not None:
            self._speak_worker.parar()
            self._speak_worker.wait(2000)
        super().closeEvent(event)

    def _start_loading(self):
        self.status_label.setText("Iniciando o Ultron (memória, plugins, IA)...")
        self.send_btn.setEnabled(False)
        self.input_line.setEnabled(False)
        self.mic_btn.setEnabled(False)
        self.orb.set_thinking(True)
        self._append_jarvis("Um momento, estou iniciando...")

        self._loader = _JarvisLoader(self.user_id, parent=self)
        self._loader.pronto.connect(self._on_jarvis_pronto)
        self._loader.falhou.connect(self._on_jarvis_falhou)
        self._loader.start()

    def _on_jarvis_pronto(self, jarvis):
        self.jarvis = jarvis
        self.orb.set_thinking(False)
        self.send_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self.mic_btn.setEnabled(True)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self._greet()

    def _on_jarvis_falhou(self, erro: str):
        self.orb.set_thinking(False)
        self.status_label.setText("Falha ao iniciar")
        self._append_jarvis(f"Erro ao iniciar o Ultron: {erro}")

    def _on_mic_clicked(self):
        if self._listen_worker is not None or self.jarvis is None:
            return
        self.mic_btn.setEnabled(False)
        self.input_line.setEnabled(False)
        self.status_label.setText("Ouvindo...")
        self.orb.set_listening(True)

        self._listen_worker = _ListenWorker(parent=self)
        self._listen_worker.ouviu.connect(self._on_ouviu)
        self._listen_worker.falhou.connect(self._on_falhou_ouvir)
        self._listen_worker.start()

    def _on_ouviu(self, texto: str):
        self.orb.set_listening(False)
        self.mic_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self._listen_worker = None
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        if texto:
            self.input_line.setText(texto)
            self._on_send()
        else:
            self._append_jarvis("(não consegui entender o que você disse, tente de novo)")

    def _on_falhou_ouvir(self, erro: str):
        self.orb.set_listening(False)
        self.mic_btn.setEnabled(True)
        self.input_line.setEnabled(True)
        self._listen_worker = None
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self._append_jarvis(f"[erro ao ouvir] {erro}")

    def _animar_pensando(self):
        self._pensando_dots = (self._pensando_dots + 1) % 4
        self.status_label.setText("Ultron está pensando" + "." * self._pensando_dots)

    def _toggle_voice(self):
        self._voice_enabled = self.voice_btn.isChecked()
        self.voice_btn.setText("Voz: ligada" if self._voice_enabled else "Voz: desligada")

    def _texto_autonomo_btn(self, ligado: bool) -> str:
        return "Modo Autônomo: ⬤ ligado" if ligado else "Modo Autônomo: ○ desligado"

    def _toggle_modo_autonomo(self):
        ligado = self.autonomo_btn.isChecked()
        self.autonomo_btn.setText(self._texto_autonomo_btn(ligado))
        settings = get_settings()
        settings.set("personalidade.modo_autonomo", ligado)
        settings.save()
        if ligado:
            minutos = settings.get("personalidade.modo_autonomo_ociosidade_minutos", 5)
            self._append_jarvis(
                f"Modo Autônomo ativado. Quando o PC ficar {minutos} minuto(s) sem uso, executo "
                'sozinho o próximo objetivo cadastrado -- diga "novo objetivo autônomo: <o quê>" '
                "pra cadastrar o que devo fazer."
            )
        else:
            self._append_jarvis("Modo Autônomo desativado -- não vou mais trabalhar sozinho no ócio.")

    def _ensure_speak_worker(self):
        """Cria o worker de fala sob demanda, na primeira vez que
        alguma resposta precisar ser falada -- assim quem nunca liga
        o som (ou não tem `pyttsx3` instalado) nunca paga esse custo."""
        if self._speak_worker is not None:
            return self._speak_worker
        try:
            robotic = bool(get_settings().get("personalidade.voz_robotica", False))
            tts = TextToSpeech(robotic=robotic)
            if not tts.available():
                self._speak_worker = False
                return False
            worker = _SpeakWorker(tts, parent=self)
            worker.start()
            self._speak_worker = worker
        except Exception:
            self._speak_worker = False
        return self._speak_worker

    def _falar(self, texto: str):
        if not self._voice_enabled:
            return
        worker = self._ensure_speak_worker()
        if worker:
            worker.enqueue(texto)

    def _abrir_dialogo_login(self):
        """Diálogo pra salvar um login de site (automacao/logins_web.py)
        com o campo de senha mascarado (QLineEdit.Password) -- chama
        `logins_web.salvar_login()` DIRETO, sem passar pelo chat/
        `Ultron.process()`, porque este último grava toda mensagem no
        histórico de conversa antes de qualquer plugin rodar. Se a
        senha viesse digitada no chat, ela ficaria em texto puro no
        banco de dados (e nos backups automáticos) -- ver aviso em
        plugins/logins_web.py."""
        dialogo = QDialog(self)
        dialogo.setWindowTitle("Salvar login de site")
        form = QFormLayout(dialogo)

        site_edit = QLineEdit()
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://exemplo.com/login")
        usuario_edit = QLineEdit()
        senha_edit = QLineEdit()
        senha_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Site (nome curto):", site_edit)
        form.addRow("URL de login:", url_edit)
        form.addRow("Usuário/e-mail:", usuario_edit)
        form.addRow("Senha:", senha_edit)

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.accepted.connect(dialogo.accept)
        botoes.rejected.connect(dialogo.reject)
        form.addRow(botoes)

        if dialogo.exec() != QDialog.Accepted:
            return

        site = site_edit.text().strip()
        url = url_edit.text().strip()
        usuario = usuario_edit.text().strip()
        senha = senha_edit.text()
        if not (site and url and usuario and senha):
            QMessageBox.warning(self, "Ultron", "Preencha todos os campos.")
            return

        try:
            from automacao import logins_web
            if not logins_web.available():
                QMessageBox.warning(
                    self, "Ultron",
                    "Instale 'keyring' e 'playwright' (requirements-automacao.txt) "
                    "para eu guardar e usar logins de sites.",
                )
                return
            logins_web.salvar_login(site, url, usuario, senha)
        except Exception as e:
            QMessageBox.critical(self, "Ultron", f"Falha ao salvar login: {e}")
            return

        QMessageBox.information(
            self, "Ultron",
            f'Login de "{site}" salvo com segurança. Diga "loga no {site}" no chat quando quiser usar.',
        )

    def _build_tray(self):
        """Registra esta janela como notifier (automacao/notify.py):
        quando um lembrete dispara, ou um comentário automático sobre
        a atividade do usuário é gerado (plugins/observation.py),
        mostra um balão na bandeja do sistema e também posta a
        mensagem no chat."""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        self.tray.setToolTip("Ultron")
        self.tray.show()

        self._notify_bridge = _NotifyBridge()
        self._notify_bridge.fired.connect(self._on_notification)
        try:
            from automacao.notify import add_notifier
            add_notifier(self._notify_bridge.fired.emit)
        except Exception:
            pass

    def _on_notification(self, titulo: str, mensagem: str):
        self.tray.showMessage(titulo, mensagem, QSystemTrayIcon.Information, 8000)
        self._append_jarvis(f"[{titulo}] {mensagem}")
        self._falar(mensagem)

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #100606, stop:0.5 #000000, stop:1 #070303);"
        )
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        title = QLabel(NOME.upper())
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #ff5f52; letter-spacing: 8px; background: transparent;")
        title.setFont(QFont("Consolas", 22, QFont.Bold))
        title_glow = QGraphicsDropShadowEffect(title)
        title_glow.setBlurRadius(28)
        title_glow.setColor(QColor(255, 60, 45, 200))
        title_glow.setOffset(0, 0)
        title.setGraphicsEffect(title_glow)
        layout.addWidget(title)

        self.orb = UltronEye()
        self.orb.setFixedHeight(240)
        layout.addWidget(self.orb)

        status_row = QHBoxLayout()
        self.status_label = QLabel(f"Pronto — sessão de {self.user_id}")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #6b7280; font-size: 12px; background: transparent;")
        status_row.addWidget(self.status_label, stretch=1)

        pill_style = (
            "QPushButton { background-color: #241515; color: #b0a3a3; "
            "border-radius: 10px; padding: 5px 12px; font-size: 11px; border: 1px solid #382323; } "
            "QPushButton:hover { background-color: #351f1f; } "
            "QPushButton:checked { background-color: #c22a1f; color: #200404; "
            "font-weight: bold; border-color: #c22a1f; }"
        )

        self.voice_btn = QPushButton("Voz: ligada")
        self.voice_btn.setCheckable(True)
        self.voice_btn.setChecked(True)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setStyleSheet(pill_style)
        self.voice_btn.clicked.connect(self._toggle_voice)
        status_row.addWidget(self.voice_btn)

        self.login_btn = QPushButton("Salvar login")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setStyleSheet(pill_style)
        self.login_btn.clicked.connect(self._abrir_dialogo_login)
        status_row.addWidget(self.login_btn)

        # Modo Autônomo (automacao/modo_autonomo.py): mesmo interruptor do
        # comando de chat "ativa/desativa o modo autônomo", só que também
        # como botão -- lê o estado atual do config na abertura, pra não
        # mostrar "desligado" se você já tinha ligado por comando antes.
        autonomo_ligado = bool(get_settings().get("personalidade.modo_autonomo", False))
        self.autonomo_btn = QPushButton(self._texto_autonomo_btn(autonomo_ligado))
        self.autonomo_btn.setCheckable(True)
        self.autonomo_btn.setChecked(autonomo_ligado)
        self.autonomo_btn.setCursor(Qt.PointingHandCursor)
        self.autonomo_btn.setStyleSheet(pill_style)
        self.autonomo_btn.setToolTip(
            "Quando ligado, o Ultron executa sozinho os objetivos cadastrados assim que o PC "
            "ficar alguns minutos sem uso (diga \"novo objetivo autônomo: <o quê>\" pra cadastrar)."
        )
        self.autonomo_btn.clicked.connect(self._toggle_modo_autonomo)
        status_row.addWidget(self.autonomo_btn)

        layout.addLayout(status_row)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self._chat_log_style_normal = (
            "QTextEdit { background-color: rgba(18, 10, 10, 0.94); color: #e7e5e5; "
            "border: 1px solid #331c1c; border-radius: 14px; padding: 16px; } "
            "QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; } "
            "QScrollBar::handle:vertical { background: #472626; border-radius: 5px; min-height: 24px; } "
            "QScrollBar::handle:vertical:hover { background: #5c3434; } "
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        self._chat_log_style_flash = self._chat_log_style_normal.replace(
            "border: 1px solid #331c1c;", "border: 1px solid #c22a1f;"
        )
        self.chat_log.setStyleSheet(self._chat_log_style_normal)
        self.chat_log.setFont(QFont("Consolas", 11))
        chat_glow = QGraphicsDropShadowEffect(self.chat_log)
        chat_glow.setBlurRadius(40)
        chat_glow.setColor(QColor(200, 30, 25, 60))
        chat_glow.setOffset(0, 0)
        self.chat_log.setGraphicsEffect(chat_glow)
        layout.addWidget(self.chat_log, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setFixedWidth(46)
        self.mic_btn.setStyleSheet(
            "QPushButton { background-color: #241515; color: #b0a3a3; "
            "border-radius: 10px; padding: 10px; font-size: 15px; border: 1px solid #382323; } "
            "QPushButton:hover { background-color: #351f1f; } "
            "QPushButton:disabled { background-color: #2b1d1d; color: #63504e; }"
        )
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        input_row.addWidget(self.mic_btn)

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Digite uma mensagem para o Ultron...")
        self.input_line.setStyleSheet(
            "QLineEdit { background-color: #1b1010; color: #fbf9f9; "
            "border: 1px solid #382323; border-radius: 10px; padding: 12px 14px; font-size: 13px; } "
            "QLineEdit:focus { border: 1px solid #c22a1f; }"
        )
        self.input_line.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_line, stretch=1)

        self.send_btn = QPushButton("Enviar")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #b5220e, stop:1 #ee4422); color: #1f0704; "
            "border-radius: 10px; padding: 12px 26px; font-weight: bold; border: none; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #c93214, stop:1 #f75c38); } "
            "QPushButton:disabled { background: #2b1d1d; color: #80706b; }"
        )
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)
        self.input_line.setFocus()

    def _greet(self):
        self._append_jarvis(
            "Ultron pronto. Digite /ajuda para ver o que eu sei fazer, ou peça "
            "para eu abrir um programa (ex.: \"abra o navegador\")."
        )
        if self.jarvis.ia_manager is None:
            self._append_jarvis(
                "Nenhum provedor de IA externo configurado ainda (isso é "
                "opcional). Para configurar, rode 'python main.py --texto' e "
                "use o comando /configurarapi."
            )

    def _flash_chat(self):
        """Pisca a borda do chat brevemente quando uma mensagem nova
        chega -- QTextEdit já usa `setGraphicsEffect` pro glow (só
        aceita UM efeito por vez), então em vez de uma animação de
        opacidade via QGraphicsOpacityEffect (que substituiria o glow),
        o "flash" aqui troca a cor da borda via stylesheet por um
        instante e volta, sem mexer no efeito gráfico existente."""
        self.chat_log.setStyleSheet(self._chat_log_style_flash)
        QTimer.singleShot(280, lambda: self.chat_log.setStyleSheet(self._chat_log_style_normal))

    def _append_user(self, text: str):
        self.chat_log.append(
            f'<div style="margin-top:6px; margin-bottom:14px; margin-left:60px; '
            f'padding:10px 14px; background-color:#291616; border-radius:12px; color:#fdf1f0;">'
            f'<b style="color:#eaa79e;">Você</b><br>{html.escape(text)}</div>'
        )
        self._flash_chat()

    def _append_jarvis(self, text: str):
        body = html.escape(text).replace("\n", "<br>")
        self.chat_log.append(
            f'<div style="margin-top:6px; margin-bottom:14px; margin-right:60px; '
            f'padding:10px 14px; background-color:#261010; border-radius:12px; '
            f'border-left:3px solid #c22a1f; color:#e7e5e5;">'
            f'<b style="color:#ff5f52;">{NOME}</b><br>{body}</div>'
        )
        self.chat_log.moveCursor(QTextCursor.End)
        self._flash_chat()

    def _on_send(self):
        text = self.input_line.text().strip()
        if not text or self._worker is not None or self.jarvis is None:
            return
        self.input_line.clear()
        self._append_user(text)

        if text.lower() in ("/sair", "/exit", "/quit"):
            self.close()
            return

        self.send_btn.setEnabled(False)
        self._pensando_dots = 0
        self.status_label.setText("Ultron está pensando")
        self._pensando_timer.start()
        self._acender_nucleo(text)
        self._resposta_inicio = time.monotonic()

        self._worker = _ProcessWorker(self.jarvis, text, parent=self)
        self._worker.done.connect(self._on_response)
        self._worker.start()

    def _acender_nucleo(self, text: str):
        """Escolhe o "modo" do olho (gui/eye.py) pela cara da mensagem --
        pesquisar EJETA faíscas pra fora, aprender puxa partículas de
        dado PRA DENTRO, o resto é o trabalho normal (pulso/energia). É
        só um sinal visual pelo tipo do pedido; qualquer um deles ainda é
        o Ultron processando."""
        low = text.lower()
        if any(k in low for k in ("pesquisa", "procura na internet", "navega na internet",
                                   "investiga", "descubra", "descobre", "busca na")):
            self.orb.set_searching(True)
        elif any(k in low for k in ("aprend", "habilidade", "inventa uma", "sonha uma", "consolida")):
            self.orb.set_learning(True)
        else:
            self.orb.set_thinking(True)

    # Duração mínima que o núcleo fica "aceso" (pensando/aprendendo/
    # pesquisando) antes de voltar ao ocioso -- MUITAS respostas
    # (comandos locais, sem IA) voltam em bem menos que isso, e sem um
    # piso a animação praticamente não dava tempo de ficar visível
    # (só um "pisca" de poucos quadros) antes de já reverter -- por
    # isso parecia "não funcionar", mesmo a lógica de cor/energia
    # estando correta por baixo.
    _DURACAO_MINIMA_NUCLEO = 0.9

    def _on_response(self, resposta: str):
        decorrido = time.monotonic() - self._resposta_inicio
        faltam = self._DURACAO_MINIMA_NUCLEO - decorrido
        if faltam > 0:
            QTimer.singleShot(int(faltam * 1000), lambda: self._finalizar_resposta(resposta))
        else:
            self._finalizar_resposta(resposta)

    def _finalizar_resposta(self, resposta: str):
        self._pensando_timer.stop()
        self._append_jarvis(resposta)
        self.status_label.setText(f"Pronto — sessão de {self.user_id}")
        self.orb.set_thinking(False)
        self.send_btn.setEnabled(True)
        self._worker = None
        self._falar(resposta)


def _ask_username() -> str:
    """Sugere o último usuário usado (config.json -> geral.usuario_padrao)
    em vez de sempre cair pro literal "default_user" -- sem isso, digitar
    o nome numa sessão e só apertar ENTER na próxima criava um perfil/
    memória SEPARADO a cada vez, e o Ultron parecia "esquecer" tudo
    porque, na prática, estava conversando com um usuário diferente."""
    settings = get_settings()
    padrao = settings.get("geral.usuario_padrao", "default_user")
    text, ok = QInputDialog.getText(
        None, "Ultron", f"Nome de usuário (ENTER para continuar como '{padrao}'):",
        QLineEdit.Normal, "",
    )
    if not ok or not text.strip():
        return padrao
    digitado = text.strip()
    if digitado != padrao:
        settings.set("geral.usuario_padrao", digitado)
        settings.save()
    return digitado


def _forcar_foco_win32(window):
    """AttachThreadInput: o jeito "de verdade" de um processo trazer a
    própria janela pro primeiro plano no Windows, mesmo com o bloqueio
    de foco ativo. `SetForegroundWindow` sozinho só funciona se quem
    chama JÁ é o processo em primeiro plano -- testado e confirmado
    neste projeto: rodando de um terminal que estava em foco, a chamada
    funcionava; mas o PRÓPRIO processo do Ultron chamando
    `activateWindow()`/`SetForegroundWindow` de dentro de si mesmo,
    logo depois de iniciar (como acontece com qualquer app lançado por
    um atalho/script), era recusada -- a janela existia, maximizada,
    visível, mas o foco continuava com quem lançou o processo. O
    workaround documentado da própria Microsoft pra esse bloqueio:
    "grudar" temporariamente a thread de entrada da janela que está em
    foco na nossa, chamar SetForegroundWindow (agora permitido, pois as
    threads contam como uma só pro Windows), e desgrudar em seguida."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()

        anexado = False
        if foreground_thread and foreground_thread != current_thread:
            anexado = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE (garante que não está minimizada)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        finally:
            if anexado:
                user32.AttachThreadInput(foreground_thread, current_thread, False)
    except Exception:
        pass


def _forcar_foco(window):
    """Traz a janela pra frente DE VERDADE. O Windows bloqueia um
    processo em segundo plano de "roubar" o foco de quem está em uso
    (SetForegroundWindow restrito) -- reproduzido e confirmado: a
    janela abria (existia, maximizada, IsWindowVisible=True) mas ficava
    atrás de qualquer outra janela em foco, parecendo "não abriu" pro
    usuário mesmo o processo estando de pé e respondendo. Combina duas
    táticas: o truque Qt de "sempre no topo" por um instante (funciona
    na maioria dos casos) e, no Windows, o AttachThreadInput via WinAPI
    direto (mais confiável, não depende do gerenciador de janelas
    aceitar o WindowStaysOnTopHint)."""
    window.setWindowState(window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
    window.setWindowFlags(window.windowFlags() | Qt.WindowStaysOnTopHint)
    window.show()
    _forcar_foco_win32(window)
    QTimer.singleShot(200, lambda: (
        window.setWindowFlags(window.windowFlags() & ~Qt.WindowStaysOnTopHint),
        window.show(),
        window.raise_(),
        window.activateWindow(),
        _forcar_foco_win32(window),
    ))


def _abrir_janela_principal(app, user_id: str):
    if not user_id or not user_id.strip():
        user_id = _ask_username()
    window = MainWindow(user_id)
    # guarda a referência no app pra não ser coletada pelo GC quando a
    # função de callback da intro retornar.
    app._jarvis_window = window
    # Abre maximizada (ocupa a tela toda, mas mantém barra de título/
    # botões e a barra de tarefas do Windows continua visível -- pedido
    # explícito do usuário, "tela cheia" no sentido maximizado, não
    # kiosk/borderless). resize() em __init__ continua servindo de
    # tamanho de volta caso o usuário desmaximize manualmente depois.
    window.showMaximized()
    _forcar_foco(window)


def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    usar_intro = bool(get_settings().get("geral.intro_animada", True))
    if not usar_intro:
        _abrir_janela_principal(app, _ask_username())
        sys.exit(app.exec())

    # Intro cinematográfica (gui/intro.py): partículas -> "cérebro
    # digital" -> logo -> identificação do operador. Ao terminar (ou
    # pular com Esc), abre a janela principal com o operador
    # identificado. Qualquer falha na intro cai pro fluxo simples de
    # sempre, pra nunca impedir o Jarvis de abrir.
    try:
        from gui.intro import IntroSequence

        intro = IntroSequence()
        intro.setWindowTitle(NOME)
        intro.resize(880, 680)
        app._jarvis_intro = intro

        def _ao_concluir(nome: str):
            intro.close()
            _abrir_janela_principal(app, nome)

        intro.concluido.connect(_ao_concluir)
        # Maximizada também -- senão a intro aparece pequena e a janela
        # principal "salta" pra tela cheia logo em seguida, inconsistente.
        intro.showMaximized()
        _forcar_foco(intro)
    except Exception:
        _abrir_janela_principal(app, _ask_username())

    sys.exit(app.exec())
