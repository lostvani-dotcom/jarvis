"""
gui/intro.py
============
Sequência de abertura cinematográfica do Ultron (só a GUI). Tudo
desenhado com QPainter, sem imagens/vídeos externos -- mesma filosofia
do gui/orb.py.

Fases ("O Olho do Ultron"):
  1. BOOT       -- tela preta; um ponto vermelho pulsa lentamente no
                   centro, se transforma num olho robótico (íris +
                   pupila em fenda), circuitos surgem ao redor com um
                   leve zoom, e tudo dá lugar ao logo (NOME em
                   maiúsculas) com um brilho vermelho percorrendo as
                   letras + "INITIALIZING SYSTEMS...". Voz: "Cognitive
                   Core initialized."
  2. SCAN       -- uma linha varre a tela ("Scanning..."), e o Ultron
                   procura um operador registrado.
  3a. Operador JÁ registrado -> "Operator recognized" + voz "Que bom
      revê-lo, <nome>." e segue direto pra interface.
  3b. NENHUM operador -> círculo holográfico + prompt "Operator Name:",
      o usuário digita (cada letra dá um brilho), "Identity Registered
      ✓", "Prazer em conhecê-lo, <nome>." e o nome é salvo.

Robusto por design: qualquer falha aqui NUNCA deve impedir o Ultron de
abrir -- run_gui() (gui/app.py) cai pro diálogo simples de sempre se a
intro falhar, e a intro é pulável (Esc/clique). A voz é opcional e roda
numa thread separada; sem `pyttsx3`, só o visual toca.

Configurável: `geral.intro_animada` (true por padrão). O operador fica
salvo em `geral.usuario_padrao` (o mesmo id de sessão já usado pela
memória) -- assim da segunda vez em diante ele é reconhecido.
"""

import math
import random
import threading
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from config.settings import get_settings
from core.personality import NOME

_VERMELHO = QColor(210, 20, 20)
_VERMELHO_CLARO = QColor(255, 70, 60)
_N_ESTRELAS = 90

# Duração (segundos) de cada sub-fase dentro do BOOT (olho) -- somadas
# com LOGO (13s) e SCAN (11s) em _tick(), o total até abrir a tela de
# nome do operador fica em ~40s (pedido explícito de 2026-07-06:
# "aumente a intro pra 40 segundos").
_BOOT_DURACAO = 16.0
_OLHO_PONTO_FIM = 3.4       # ponto pulsando, antes de virar olho
_OLHO_CRESCE_FIM = 9.5      # olho totalmente formado a partir daqui
_OLHO_CIRCUITOS_INICIO = 7.2
_OLHO_ZOOM_INICIO = 10.5

# Log de inicialização que aparece linha a linha durante a formação do
# olho (fase boot) -- dá a sensação de uma IA de verdade subindo os
# subsistemas, deixando a intro "mais completa" sem alongar o tempo.
# (segundo_em_que_aparece, texto). O último é proposital perto do fim do
# boot pra emendar no logo.
_BOOT_LOG = (
    (0.6, "> Inicializando núcleo cognitivo..."),
    (2.2, "> Reator de processamento .......... ONLINE"),
    (4.0, "> Bancos de memória ................ MONTADOS"),
    (5.6, "> Base de conhecimento ............. CARREGADA"),
    (7.2, "> Rede neural sensorial ............ ATIVA"),
    (8.8, "> Módulos de automação ............. PRONTOS"),
    (10.4, "> Protocolos de voz ................ CALIBRADOS"),
    (12.0, "> Consciência situacional .......... ATIVA"),
    (13.6, "> Todos os sistemas nominais."),
)


def _falar_async(texto: str):
    """Fala uma linha em voz alta numa thread daemon -- best-effort, e
    NUNCA levanta pra fora (se não houver TTS, só não fala). Cada linha
    da intro é bem espaçada da seguinte, então não há sobreposição de
    fala na prática."""
    def _run():
        try:
            from voz.tts import TextToSpeech
            tts = TextToSpeech(robotic=bool(get_settings().get("personalidade.voz_robotica", True)))
            if tts.available():
                tts.speak(texto)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


class IntroSequence(QWidget):
    """Emite `concluido(nome_operador)` quando termina (ou é pulada)."""

    concluido = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("background: #000000;")

        settings = get_settings()
        padrao = settings.get("geral.usuario_padrao", "default_user")
        self._operador_existente = padrao if (padrao and padrao != "default_user") else None

        self._t0 = time.monotonic()
        self._fase = "boot"
        self._fase_t0 = self._t0
        self._voz_boot = False
        self._voz_operador = False
        self._voz_fim = False
        self._nome_digitado = ""
        self._key_glow = 0.0
        self._finalizado = False

        # Poeira estelar ambiente (visível em toda a intro, atrás de tudo)
        # -- posições normalizadas (0..1) pra funcionar em qualquer tamanho
        # de janela, com fase própria de "cintilação" por estrela.
        self._estrelas = [
            (random.uniform(0, 1), random.uniform(0, 1), random.uniform(0.5, 2.0),
             random.uniform(0, 2 * math.pi), random.uniform(0.5, 1.4))
            for _ in range(_N_ESTRELAS)
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ---------- ciclo de vida ----------

    def showEvent(self, _e):
        self.setFocus()

    def _elapsed(self) -> float:
        return time.monotonic() - self._fase_t0

    def _mudar_fase(self, fase: str):
        self._fase = fase
        self._fase_t0 = time.monotonic()

    def _tick(self):
        el = self._elapsed()

        if self._fase == "boot":
            # ponto -> olho -> circuitos -> zoom (ver _desenhar_olho).
            # Duração total de _BOOT_DURACAO (não uma animação de física
            # de partículas mais -- tudo procedural, função direta do
            # tempo decorrido).
            if el > _BOOT_DURACAO:
                self._mudar_fase("logo")

        elif self._fase == "logo":
            if not self._voz_boot:
                self._voz_boot = True
                _falar_async("Cognitive Core initialized.")
            if el > 13.0:
                self._mudar_fase("scan")

        elif self._fase == "scan":
            if el > 11.0:
                if self._operador_existente:
                    self._mudar_fase("reconhecido")
                else:
                    self._mudar_fase("operador_input")

        elif self._fase == "reconhecido":
            if not self._voz_fim:
                self._voz_fim = True
                _falar_async(f"Que bom revê-lo, {self._operador_existente}.")
            if el > 3.2:
                self._finalizar(self._operador_existente)

        elif self._fase == "operador_input":
            if not self._voz_operador:
                self._voz_operador = True
                _falar_async("Bem-vindo. Antes de continuarmos, preciso identificar meu operador.")
                # Som do sistema (não só voz) -- percebido MESMO se a janela
                # não estiver em primeiro plano por algum motivo (bug real
                # encontrado: o Windows pode recusar trazer uma janela nova
                # pra frente dependendo de como o processo foi iniciado,
                # ver gui/app.py:_forcar_foco). Sem esse aviso audível, a
                # tela "esperando o nome do operador" ficava esperando em
                # silêncio, atrás de outra janela, parecendo "não abriu".
                try:
                    from automacao.notify import notify
                    notify("Ultron", "Aguardando você digitar seu nome...", sound=True)
                except Exception:
                    pass
            # Nunca fica esperando digitação PRA SEMPRE em silêncio --
            # bug real encontrado: sem isso, se a janela não estivesse em
            # foco (ou o usuário não percebesse que precisava digitar), a
            # intro ficava parada aqui indefinidamente parecendo "não
            # abriu"/travou, mesmo o processo estando de pé e rodando. Após
            # um tempo generoso sem nenhuma tecla, segue como "default_user"
            # (mesmo comportamento de apertar Enter em branco).
            if el > 25.0 and not self._nome_digitado.strip():
                self._finalizar("default_user")

        elif self._fase == "registrado":
            if not self._voz_fim:
                self._voz_fim = True
                _falar_async(f"Prazer em conhecê-lo, {self._nome_digitado}.")
            if el > 3.2:
                self._finalizar(self._nome_digitado)

        self._key_glow = max(0.0, self._key_glow - 0.05)
        self.update()

    def _finalizar(self, nome: str):
        if self._finalizado:
            return
        self._finalizado = True
        self._timer.stop()
        nome = (nome or "").strip() or "default_user"
        if nome != self._operador_existente:
            try:
                settings = get_settings()
                settings.set("geral.usuario_padrao", nome)
                settings.save()
            except Exception:
                pass
        self.concluido.emit(nome)

    # ---------- interação ----------

    def keyPressEvent(self, event):
        # Esc pula a intro inteira -- usa o operador existente, ou cai
        # pro diálogo simples (nome vazio -> run_gui trata).
        if event.key() == Qt.Key_Escape:
            self._finalizar(self._operador_existente or "")
            return

        if self._fase != "operador_input":
            # Enquanto não está na fase de digitar, qualquer tecla adianta
            # até lá (deixa pular a abertura sem perder o registro).
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                if self._operador_existente:
                    self._finalizar(self._operador_existente)
                else:
                    self._mudar_fase("operador_input")
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._nome_digitado.strip():
                self._mudar_fase("registrado")
            return
        if event.key() == Qt.Key_Backspace:
            self._nome_digitado = self._nome_digitado[:-1]
            self._key_glow = 1.0
            return
        texto = event.text()
        if texto and texto.isprintable() and len(self._nome_digitado) < 24:
            self._nome_digitado += texto
            self._key_glow = 1.0

    # ---------- desenho ----------

    def paintEvent(self, _e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        self._desenhar_fundo(painter)

        if self._fase in ("boot", "logo"):
            self._desenhar_olho(painter)
        if self._fase == "boot":
            self._desenhar_boot_log(painter)
        if self._fase == "logo":
            self._desenhar_logo(painter)
        elif self._fase in ("scan", "reconhecido"):
            self._desenhar_scan(painter)
        elif self._fase in ("operador_input", "registrado"):
            self._desenhar_operador(painter)

        painter.end()

    def _desenhar_fundo(self, painter: QPainter):
        """Vinheta sutil + poeira estelar cintilante -- roda em TODAS as
        fases, atrás de tudo, pra dar profundidade/atmosfera em vez de
        um preto totalmente chapado. Custo baixo (só ~90 pontos +
        1 gradiente radial), sem afetar o tempo/lógica da intro."""
        w, h = self.width(), self.height()
        vinheta = QRadialGradient(QPointF(w / 2, h * 0.42), max(w, h) * 0.75)
        vinheta.setColorAt(0.0, QColor(18, 5, 5, 255))
        vinheta.setColorAt(0.55, QColor(6, 2, 2, 255))
        vinheta.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.setPen(Qt.NoPen)
        painter.setBrush(vinheta)
        painter.drawRect(self.rect())

        t = time.monotonic() - self._t0
        painter.setPen(Qt.NoPen)
        for nx, ny, raio, fase, vel in self._estrelas:
            brilho = 0.5 + 0.5 * math.sin(t * vel + fase)
            alpha = int(30 + 90 * brilho)
            cor = QColor(255, 210, 200, alpha) if brilho > 0.75 else QColor(200, 60, 55, alpha)
            painter.setBrush(cor)
            painter.drawEllipse(QPointF(nx * w, ny * h), raio, raio)

    def _desenhar_boot_log(self, painter: QPainter):
        """Linhas de inicialização subindo no canto inferior esquerdo,
        aparecendo conforme o tempo do boot passa -- só as que já
        'aconteceram', com a mais recente destacada (a última acesa)."""
        el = self._elapsed()
        visiveis = [(t, txt) for (t, txt) in _BOOT_LOG if el >= t]
        if not visiveis:
            return
        painter.setFont(QFont("Consolas", 11))
        x = 46
        y0 = self.height() - 40 - (len(visiveis) - 1) * 22
        for i, (t, txt) in enumerate(visiveis):
            recente = (i == len(visiveis) - 1)
            # fade-in de cada linha nos primeiros 0.5s dela
            a = int(min(1.0, (el - t) / 0.5) * 255)
            cor = QColor(255, 90, 70, a) if recente else QColor(150, 40, 35, int(a * 0.7))
            painter.setPen(cor)
            painter.drawText(x, y0 + i * 22, txt)

    def _desenhar_olho(self, painter: QPainter):
        """"O Olho do Ultron": ponto vermelho pulsando -> olho robótico
        (íris + pupila em fenda) -> circuitos surgindo ao redor -> leve
        zoom. Tudo procedural (função direta do tempo decorrido), sem
        partículas com estado próprio -- mais simples e sempre
        perfeitamente centralizado (não hérda o antigo bug de alvo
        travado no tamanho da janela no momento da geração)."""
        cx, cy = self.width() / 2, self.height() / 2

        # Durante a fase "logo", o olho continua (congelado no fim do
        # boot) só desvanecendo -- soma _BOOT_DURACAO pra manter o
        # progresso de crescimento/zoom no ponto em que parou.
        if self._fase == "logo":
            el = _BOOT_DURACAO + self._elapsed()
            fade = max(0.0, 1.0 - self._elapsed() / 2.0)
        else:
            el = self._elapsed()
            fade = 1.0

        if el < _OLHO_PONTO_FIM:
            pulso = 0.55 + 0.45 * math.sin(el * 2.6)
            raio = 3.5 + 2.5 * pulso
            cor = QColor(_VERMELHO_CLARO)
            cor.setAlpha(int(255 * fade))
            painter.setPen(Qt.NoPen)
            painter.setBrush(cor)
            painter.drawEllipse(QPointF(cx, cy), raio, raio)
            grad = QRadialGradient(QPointF(cx, cy), 46)
            c0 = QColor(_VERMELHO)
            c0.setAlpha(int(110 * pulso * fade))
            grad.setColorAt(0.0, c0)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(grad)
            painter.drawEllipse(QPointF(cx, cy), 46, 46)
            return

        prog_olho = min(1.0, (el - _OLHO_PONTO_FIM) / (_OLHO_CRESCE_FIM - _OLHO_PONTO_FIM))
        prog_zoom = max(0.0, min(1.0, (el - _OLHO_ZOOM_INICIO) / 3.0))
        zoom = 1.0 + 0.18 * prog_zoom

        raio_iris = (16 + 42 * prog_olho) * zoom
        raio_esclera_x = raio_iris * 1.7
        raio_esclera_y = raio_esclera_x * 0.6

        # anel externo -- órbita/lente mecânica
        pen = QPen(QColor(150, 20, 20, int(210 * prog_olho * fade)))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), raio_esclera_x, raio_esclera_y)

        # íris -- glow radial vermelho
        grad = QRadialGradient(QPointF(cx, cy), raio_iris)
        c0 = QColor(255, 60, 45)
        c0.setAlpha(int(235 * fade))
        c1 = QColor(190, 15, 15)
        c1.setAlpha(int(180 * fade))
        grad.setColorAt(0.0, c0)
        grad.setColorAt(0.55, c1)
        grad.setColorAt(1.0, QColor(40, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, cy), raio_iris, raio_iris)

        # pupila -- fenda vertical escura (olho de réptil/robô)
        fenda_w = max(2.0, raio_iris * 0.16)
        fenda_h = raio_iris * 0.85
        painter.setBrush(QColor(8, 0, 0, int(250 * fade)))
        painter.drawEllipse(QPointF(cx, cy), fenda_w, fenda_h)

        # catchlight -- um brilho pequeno e deslocado, como o reflexo
        # que um olho de verdade tem -- sem isso, o olho todo geométrico
        # parece uma textura morta em vez de algo "vivo".
        if prog_olho > 0.5:
            catch_alpha = int(200 * fade * min(1.0, (prog_olho - 0.5) / 0.3))
            painter.setBrush(QColor(255, 210, 200, catch_alpha))
            painter.drawEllipse(
                QPointF(cx - raio_iris * 0.28, cy - raio_iris * 0.32),
                raio_iris * 0.11, raio_iris * 0.11,
            )

        # circuitos radiais surgindo ao redor do olho
        if el > _OLHO_CIRCUITOS_INICIO:
            prog_circ = min(1.0, (el - _OLHO_CIRCUITOS_INICIO) / 4.2)
            n = 10
            proporcao = raio_esclera_y / raio_esclera_x
            for i in range(n):
                ang = (2 * math.pi / n) * i + el * 0.06
                r_dentro = raio_esclera_x * 1.08
                r_fora = raio_esclera_x * (1.35 + 1.1 * prog_circ)
                x1 = cx + math.cos(ang) * r_dentro
                y1 = cy + math.sin(ang) * r_dentro * proporcao
                x2 = cx + math.cos(ang) * r_fora
                y2 = cy + math.sin(ang) * r_fora * proporcao
                pen2 = QPen(QColor(200, 30, 30, int(150 * prog_circ * fade)))
                pen2.setWidthF(1.2)
                painter.setPen(pen2)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(220, 50, 40, int(190 * prog_circ * fade)))
                painter.drawEllipse(QPointF(x2, y2), 2.4, 2.4)

    def _desenhar_logo(self, painter: QPainter):
        el = self._elapsed()
        alpha = int(min(1.0, el / 1.2) * 255)
        cx, cy = self.width() / 2, self.height() / 2
        texto = NOME.upper()
        fonte = QFont("Consolas", 54, QFont.Bold)

        # Um único QPainterPath pro texto -- a base (fill fosco) e o
        # brilho que "percorre" as letras usam EXATAMENTE a mesma
        # geometria (setClipPath nele), então nunca desalinham entre si
        # (diferente de tentar casar um drawText() com um path calculado
        # à parte, que exigiria replicar manualmente a métrica de
        # baseline/alinhamento do Qt e arriscaria ficar torto).
        path = QPainterPath()
        path.addText(0, 0, fonte, texto)
        br = path.boundingRect()
        path.translate(cx - br.center().x(), cy - br.center().y())
        br = path.boundingRect()

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(150, 20, 20, alpha))
        painter.drawPath(path)

        # O brilho percorre as letras em ciclos (não só uma vez): a fase
        # de logo agora dura 10s, e com uma única passada os ~7s finais
        # ficavam completamente estáticos, parecendo travado.
        ciclo = el % 3.5
        if ciclo < 2.6:
            prog = min(1.0, ciclo / 2.2)
            faixa_x = br.left() - 90 + (br.width() + 180) * prog
            grad = QLinearGradient(faixa_x - 70, 0, faixa_x + 70, 0)
            grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            grad.setColorAt(0.5, QColor(255, 120, 100, min(255, alpha)))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.save()
            painter.setClipPath(path)
            painter.fillRect(QRectF(faixa_x - 70, br.top() - 20, 140, br.height() + 40), grad)
            painter.restore()

        # linha HUD abaixo do logo -- "desenha" da metade pras pontas
        # conforme o texto aparece, um toque de painel de comando em vez
        # de só o texto sozinho no vazio.
        prog_linha = min(1.0, el / 1.4)
        largura_linha = max(60.0, br.width() * 0.55) * prog_linha
        y_linha = cy + br.height() / 2 + 26
        pen_linha = QPen(QColor(200, 40, 30, alpha))
        pen_linha.setWidthF(1.4)
        painter.setPen(pen_linha)
        painter.drawLine(QPointF(cx - largura_linha, y_linha), QPointF(cx + largura_linha, y_linha))

        # subtítulo em "máquina de escrever" -- caractere por caractere,
        # em vez de aparecer tudo de uma vez (mais vivo, parece um
        # terminal real inicializando).
        subtitulo = "INITIALIZING SYSTEMS..."
        n_visiveis = int(min(len(subtitulo), max(0.0, el - 0.3) / 0.05))
        texto_sub = " ".join(subtitulo[:n_visiveis])
        painter.setPen(QColor(190, 40, 30, alpha))
        painter.setFont(QFont("Consolas", 13))
        painter.drawText(
            QRectF(0, y_linha + 14, self.width(), 40), Qt.AlignHCenter | Qt.AlignTop, texto_sub,
        )

    def _desenhar_reticulo(self, painter: QPainter, alpha: int):
        """Cantos de mira estilo HUD/câmera de mira -- só decoração, dá
        uma cara de "sistema de escaneamento" mais rica que a linha
        varrendo sozinha."""
        w, h = self.width(), self.height()
        margem_x, margem_y = w * 0.12, h * 0.16
        tam = 28
        pen = QPen(QColor(210, 40, 30, alpha))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        for ex in (margem_x, w - margem_x):
            for ey in (margem_y, h - margem_y):
                dx = tam if ex == margem_x else -tam
                dy = tam if ey == margem_y else -tam
                painter.drawLine(QPointF(ex, ey), QPointF(ex + dx, ey))
                painter.drawLine(QPointF(ex, ey), QPointF(ex, ey + dy))

    def _desenhar_scan(self, painter: QPainter):
        el = self._elapsed()
        h = self.height()
        self._desenhar_reticulo(painter, int(120 + 40 * math.sin(el * 1.6)))
        # linha de varredura descendo -- vermelha, pra continuar o tema
        # do "Olho do Ultron" em vez de saltar pro azul do Jarvis antigo.
        y = (el / 1.4) % 1.0 * h
        pen = QPen(QColor(210, 30, 30, 190))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawLine(0, int(y), self.width(), int(y))
        rastro = QRadialGradient(QPointF(self.width() / 2, y), self.width())
        rastro.setColorAt(0.0, QColor(210, 30, 30, 45))
        rastro.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(rastro)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, int(y) - 30, self.width(), 60)

        painter.setPen(QColor(230, 60, 50, 230))
        painter.setFont(QFont("Consolas", 18, QFont.Bold))
        painter.drawText(
            QRectF(0, self.height() / 2 - 40, self.width(), 40), Qt.AlignCenter, "Scanning..."
        )

        if el > 1.2:
            if self._operador_existente or self._fase == "reconhecido":
                msg = f"> Operator recognized: {self._operador_existente}"
                cor = QColor(94, 234, 212, 240)
            else:
                msg = "> No operator found."
                cor = QColor(255, 170, 90, 240)
            painter.setPen(cor)
            painter.setFont(QFont("Consolas", 14))
            painter.drawText(
                QRectF(0, self.height() / 2 + 6, self.width(), 40), Qt.AlignCenter, msg
            )

    def _desenhar_operador(self, painter: QPainter):
        cx, cy = self.width() / 2, self.height() / 2
        el = self._elapsed()

        # círculo holográfico pulsante -- vermelho, pra combinar com o
        # resto do "Olho do Ultron" (antes ainda era o azul do Jarvis
        # antigo, uma inconsistência real que ficava só nesta tela).
        for i in range(3):
            raio = 150 + i * 22 + 8 * math.sin(el * 2 + i)
            cor = QColor(210, 40, 30, 60 - i * 16)
            pen = QPen(cor)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), raio, raio)

        if self._fase == "registrado":
            painter.setPen(QColor(94, 234, 212, 255))
            painter.setFont(QFont("Consolas", 20, QFont.Bold))
            painter.drawText(QRectF(0, cy - 70, self.width(), 40), Qt.AlignCenter, "Identity Registered  ✓")
            painter.setPen(QColor(230, 240, 255, 255))
            painter.setFont(QFont("Consolas", 16))
            painter.drawText(
                QRectF(0, cy - 10, self.width(), 40), Qt.AlignCenter,
                f"Prazer em conhecê-lo, {self._nome_digitado}.",
            )
            return

        painter.setPen(QColor(235, 150, 130, 235))
        painter.setFont(QFont("Consolas", 13))
        painter.drawText(
            QRectF(0, cy - 90, self.width(), 30), Qt.AlignCenter,
            "Bem-vindo. Preciso identificar meu operador.",
        )

        painter.setPen(QColor(220, 110, 95, 220))
        painter.setFont(QFont("Consolas", 13))
        painter.drawText(QRectF(0, cy - 24, self.width(), 26), Qt.AlignCenter, "Operator Name:")

        # nome digitado + cursor piscando, com brilho a cada tecla
        cursor = "▋" if int(el * 2) % 2 == 0 else " "
        texto = f"> {self._nome_digitado}{cursor}"
        glow = int(120 + 135 * self._key_glow)
        painter.setPen(QColor(255, 130, 90, min(255, glow)))
        painter.setFont(QFont("Consolas", 22, QFont.Bold))
        painter.drawText(QRectF(0, cy + 12, self.width(), 44), Qt.AlignCenter, texto)

        painter.setPen(QColor(130, 100, 95, 180))
        painter.setFont(QFont("Consolas", 10))
        painter.drawText(
            QRectF(0, self.height() - 46, self.width(), 24), Qt.AlignCenter,
            "digite seu nome e aperte ENTER   ·   ESC para pular",
        )
