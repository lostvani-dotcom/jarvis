"""
gui/eye.py
==========
"O Olho do Ultron" como núcleo da interface principal (não só a intro,
ver gui/intro.py) -- um olho robótico vermelho (íris com glow + pupila
em fenda + anel mecânico + circuitos radiais), desenhado inteiramente
com QPainter, sem imagem/vídeo externo (mesma filosofia de gui/orb.py e
gui/reactor.py).

Mantém DELIBERADAMENTE vermelho em todo estado (pedido explícito: "esse
olho deve ser vermelho") -- diferente do antigo núcleo (gui/reactor.py),
que trocava de matiz por estado (teal/verde/âmbar), aqui a distinção
entre estados é por ENERGIA/MOVIMENTO, não cor:
- ocioso: pulso lento e fraco, pupila "respirando".
- pensando: pulso mais rápido/forte, íris maior, circuitos mais vivos.
- ouvindo: glow estável, atento (menos pulso, mais brilho constante).
- aprendendo: pontos de dado voando PRA DENTRO ao longo dos circuitos
  (absorvendo informação).
- pesquisando: faíscas ejetadas PRA FORA (mesmo princípio do antigo
  "plasma do reator" em gui/reactor.py, só que como fagulhas vermelhas).

Interface compatível com o núcleo antigo (ReactorCore/MoleculeOrb):
set_thinking/set_listening/set_learning/set_searching/reset -- troca
direta em gui/app.py, sem mudar mais nada ao redor.
"""

import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

_ENERGIA = {"idle": 0.15, "thinking": 1.0, "learning": 0.8, "searching": 0.95, "listening": 0.65}
_N_CIRCUITOS = 14


class UltronEye(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._modo = "idle"
        self._energy = _ENERGIA["idle"]
        self._target_energy = _ENERGIA["idle"]
        self._t = 0.0

        self._faiscas = []   # pesquisando: ejetadas pra fora
        self._absorvidas = []  # aprendendo: viajam pra dentro

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ---------- API (compatível com o núcleo antigo) ----------

    def _set_modo(self, modo: str):
        self._modo = modo
        self._target_energy = _ENERGIA.get(modo, 0.15)

    def set_thinking(self, on: bool):
        self._set_modo("thinking" if on else "idle")

    def set_listening(self, on: bool):
        self._set_modo("listening" if on else "idle")

    def set_learning(self, on: bool):
        self._set_modo("learning" if on else "idle")

    def set_searching(self, on: bool):
        self._set_modo("searching" if on else "idle")

    def reset(self):
        self._set_modo("idle")

    # ---------- animação ----------

    def _tick(self):
        self._t += 0.016
        self._energy += (self._target_energy - self._energy) * 0.12

        if self._modo == "searching" and random.random() < 0.5:
            self._emitir_faisca()
        if self._modo == "learning" and random.random() < 0.4:
            self._emitir_absorvida()

        self._faiscas = self._avancar(self._faiscas, cresce=True)
        self._absorvidas = self._avancar(self._absorvidas, cresce=False)

        self.update()

    def _avancar(self, particulas, cresce: bool):
        vivas = []
        for p in particulas:
            p["prog"] += p["vel"]
            if p["prog"] < 1.0:
                vivas.append(p)
        return vivas

    def _raio_base(self) -> float:
        return min(self.width(), self.height()) * 0.16

    def _emitir_faisca(self):
        ang = random.uniform(0, 2 * math.pi)
        self._faiscas.append({"ang": ang, "prog": 0.0, "vel": random.uniform(0.03, 0.06)})

    def _emitir_absorvida(self):
        ang = random.uniform(0, 2 * math.pi)
        self._absorvidas.append({"ang": ang, "prog": 0.0, "vel": random.uniform(0.025, 0.05)})

    # ---------- desenho ----------

    def paintEvent(self, _e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        cx, cy = self.width() / 2, self.height() / 2
        self._desenhar_vinheta(painter, cx, cy)
        self._desenhar_circuitos(painter, cx, cy)
        self._desenhar_absorvidas(painter, cx, cy)
        self._desenhar_faiscas(painter, cx, cy)
        self._desenhar_olho(painter, cx, cy)

        painter.end()

    def _desenhar_vinheta(self, painter, cx, cy):
        v = QRadialGradient(QPointF(cx, cy), max(self.width(), self.height()) * 0.6)
        c = QColor(160, 20, 20, int(14 + 20 * self._energy))
        v.setColorAt(0.0, c)
        v.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(v))
        painter.drawRect(self.rect())

    def _pontos_circuito(self, cx, cy):
        """Geometria dos N circuitos radiais -- reaproveitada pelo
        desenho das linhas e pelas partículas que viajam ao longo delas
        (faíscas pra fora, absorção pra dentro), pra tudo ficar alinhado
        na mesma grade em vez de duas geometrias levemente diferentes."""
        raio_esclera = self._raio_base() * (1.7 + 0.15 * self._energy)
        proporcao = 0.6
        pontos = []
        for i in range(_N_CIRCUITOS):
            ang = (2 * math.pi / _N_CIRCUITOS) * i + self._t * (0.08 + 0.1 * self._energy)
            r_dentro = raio_esclera * 1.1
            r_fora = raio_esclera * 1.9
            pontos.append((ang, r_dentro, r_fora, proporcao))
        return pontos

    def _ponto_no_raio(self, cx, cy, ang, r, proporcao):
        return cx + math.cos(ang) * r, cy + math.sin(ang) * r * proporcao

    def _desenhar_circuitos(self, painter, cx, cy):
        alpha_base = int(70 + 90 * self._energy)
        for ang, r_dentro, r_fora, proporcao in self._pontos_circuito(cx, cy):
            x1, y1 = self._ponto_no_raio(cx, cy, ang, r_dentro, proporcao)
            x2, y2 = self._ponto_no_raio(cx, cy, ang, r_fora, proporcao)
            pen = QPen(QColor(190, 30, 30, alpha_base))
            pen.setWidthF(1.1)
            painter.setPen(pen)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(210, 45, 40, alpha_base))
            painter.drawEllipse(QPointF(x2, y2), 2.0, 2.0)

    def _desenhar_faiscas(self, painter, cx, cy):
        raio_esclera = self._raio_base() * (1.7 + 0.15 * self._energy)
        painter.setPen(Qt.NoPen)
        for p in self._faiscas:
            r = raio_esclera * (1.1 + 1.6 * p["prog"])
            x, y = self._ponto_no_raio(cx, cy, p["ang"], r, 0.6)
            alpha = int(220 * (1.0 - p["prog"]))
            painter.setBrush(QColor(255, 90, 60, max(0, alpha)))
            painter.drawEllipse(QPointF(x, y), 2.6, 2.6)

    def _desenhar_absorvidas(self, painter, cx, cy):
        raio_esclera = self._raio_base() * (1.7 + 0.15 * self._energy)
        painter.setPen(Qt.NoPen)
        for p in self._absorvidas:
            r = raio_esclera * (1.9 - 0.8 * p["prog"])
            x, y = self._ponto_no_raio(cx, cy, p["ang"], r, 0.6)
            alpha = int(220 * p["prog"])
            painter.setBrush(QColor(255, 200, 120, max(0, alpha)))
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)

    def _desenhar_olho(self, painter, cx, cy):
        pulso_vel = 1.4 + 2.2 * self._energy
        pulso = 0.85 + 0.15 * math.sin(self._t * pulso_vel)
        raio_iris = self._raio_base() * (1.0 + 0.35 * self._energy) * pulso
        raio_esclera_x = raio_iris * 1.7
        raio_esclera_y = raio_esclera_x * 0.6

        pen = QPen(QColor(150, 20, 20, int(180 + 60 * self._energy)))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), raio_esclera_x, raio_esclera_y)

        grad = QRadialGradient(QPointF(cx, cy), raio_iris)
        grad.setColorAt(0.0, QColor(255, 60, 45, int(200 + 55 * self._energy)))
        grad.setColorAt(0.55, QColor(190, 15, 15, int(150 + 60 * self._energy)))
        grad.setColorAt(1.0, QColor(40, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(cx, cy), raio_iris, raio_iris)

        # pupila mais estreita/focada quanto maior a energia (mais
        # "concentrado" processando) -- e um leve "piscar" periódico no
        # repouso pra não parecer uma imagem morta/estática.
        piscar = 1.0
        if self._modo == "idle":
            fase_piscar = math.sin(self._t * 0.35)
            if fase_piscar > 0.97:
                piscar = max(0.1, 1.0 - (fase_piscar - 0.97) / 0.03)
        fenda_w = max(1.5, raio_iris * (0.2 - 0.07 * self._energy)) * piscar
        fenda_h = raio_iris * 0.85 * piscar
        painter.setBrush(QColor(8, 0, 0, 250))
        painter.drawEllipse(QPointF(cx, cy), fenda_w, fenda_h)
