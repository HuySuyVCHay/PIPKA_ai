"""Игральный кубик ПИПКИ.

Как он себя ведёт:
- спокойно лежит и чуть «дышит»;
- нажали на него или сказали «ПИПКА» — подпрыгивает, кувыркается, падает
  с отскоками и останавливается на случайном числе от 1 до 6;
- пока ПИПКА думает над ответом — крутится в воздухе, а когда ответ готов,
  падает и показывает новое число.
"""

import math
import random
import time

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

# Грани: нормаль, две оси грани (вправо, вверх) и число точек.
# Противоположные грани в сумме дают 7, как у настоящего кубика.
FACES = [
    ((0, 0, 1), (1, 0, 0), (0, 1, 0), 1),
    ((0, 0, -1), (-1, 0, 0), (0, 1, 0), 6),
    ((1, 0, 0), (0, 0, -1), (0, 1, 0), 2),
    ((-1, 0, 0), (0, 0, 1), (0, 1, 0), 5),
    ((0, 1, 0), (1, 0, 0), (0, 0, -1), 3),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1), 4),
]

PIPS = {
    1: [(0, 0)],
    2: [(-0.48, 0.48), (0.48, -0.48)],
    3: [(-0.48, 0.48), (0, 0), (0.48, -0.48)],
    4: [(-0.48, -0.48), (0.48, -0.48), (-0.48, 0.48), (0.48, 0.48)],
    5: [(-0.48, -0.48), (0.48, -0.48), (0, 0), (-0.48, 0.48), (0.48, 0.48)],
    6: [(-0.48, -0.5), (-0.48, 0), (-0.48, 0.5), (0.48, -0.5), (0.48, 0), (0.48, 0.5)],
}

CAMERA = 6.0
LIGHT = (-0.45, 0.7, 0.75)
FACE_LIGHT = (250, 248, 244)   # освещённая грань
FACE_DARK = (150, 150, 172)    # грань в тени
PIP_COLOR = QColor("#1e2130")
PIP_ONE = QColor("#e5484d")    # единица — красная, как на настоящих костях

ROLL_TIME = 1.35      # сколько длится бросок, секунды
LAND_TIME = 0.9       # падение после «думания»
AIR_HEIGHT = 0.9      # высота в воздухе (в размерах кубика)


# ---------- маленькая 3D-математика (матрицы 3×3 списками) ----------
def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def _rot_x(t):
    c, s = math.cos(t), math.sin(t)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rot_y(t):
    c, s = math.cos(t), math.sin(t)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rot_z(t):
    c, s = math.cos(t), math.sin(t)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _face_to_top(number):
    """Поворот, после которого грань с этим числом смотрит вверх — как у настоящей кости."""
    for normal, axis_a, axis_b, count in FACES:
        if count == number:
            return [list(axis_a), list(normal), [-v for v in axis_b]]
    return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


# Смотрим сверху-сбоку: верхняя грань (выпавшее число) видна крупно
VIEW = _mul(_rot_x(math.radians(42)), _rot_y(math.radians(-30)))


def _ease_out(t):
    return 1 - (1 - t) ** 3


def _bounce(t):
    """Высота при падении с отскоками: 1 -> 0, два затухающих прыжка."""
    if t < 0.55:
        return 1 - (t / 0.55) ** 2
    if t < 0.8:
        u = (t - 0.55) / 0.25
        return 0.22 * (1 - (2 * u - 1) ** 2)
    u = (t - 0.8) / 0.2
    return 0.06 * (1 - (2 * u - 1) ** 2)


def _rounded_path(points, radius_share=0.18):
    """Многоугольник со скруглёнными углами: так грань похожа на настоящую кость."""
    path = QPainterPath()
    n = len(points)
    for i in range(n):
        prev_p = points[i - 1]
        cur = points[i]
        next_p = points[(i + 1) % n]
        start = QPointF(cur[0] + (prev_p[0] - cur[0]) * radius_share,
                        cur[1] + (prev_p[1] - cur[1]) * radius_share)
        end = QPointF(cur[0] + (next_p[0] - cur[0]) * radius_share,
                      cur[1] + (next_p[1] - cur[1]) * radius_share)
        if i == 0:
            path.moveTo(start)
        else:
            path.lineTo(start)
        path.quadTo(QPointF(*cur), end)
    path.closeSubpath()
    return path


class DiceWidget(QWidget):
    """Кубик, который бросают. Сигнал rolled(число) — когда кубик остановился."""

    rolled = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 210)
        self.setMaximumSize(260, 250)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.value = random.randint(1, 6)
        self.state = "idle"          # idle | roll | air | land
        self.thinking = False
        self.t0 = time.time()
        self.spin = (0.0, 0.0, 0.0)  # сколько оборотов по осям сделать за бросок

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    # ---------- что умеет снаружи ----------
    def interact(self):
        """Бросить кубик (нажатие, слово «ПИПКА», кнопка микрофона)."""
        if self.state in ("roll", "air"):
            return
        self._start_roll()

    def set_thinking(self, active):
        """Пока ИИ думает — кубик в воздухе. Ответ готов — падает на новое число."""
        self.thinking = active
        if active:
            if self.state != "air":
                self.state = "air"
                self.t0 = time.time()
        elif self.state == "air":
            self.state = "land"
            self.t0 = time.time()
            self.value = random.randint(1, 6)
            self.spin = (random.choice((1, 2)), random.choice((1, 2)), 0)

    def mousePressEvent(self, event):
        self.interact()

    # ---------- анимация ----------
    def _start_roll(self):
        self.state = "roll"
        self.t0 = time.time()
        self.value = random.randint(1, 6)
        # Целое число оборотов: в конце кубик точно встаёт ровно гранью к нам
        self.spin = (random.choice((1, 2, 2, 3)), random.choice((1, 2)), random.choice((0, 1)))

    def _finish(self):
        self.state = "air" if self.thinking else "idle"
        self.t0 = time.time()
        self.rolled.emit(self.value)

    def tick(self):
        if self.window().isMinimized():
            return
        now = time.time()
        if self.state == "roll" and now - self.t0 >= ROLL_TIME:
            self._finish()
        elif self.state == "land" and now - self.t0 >= LAND_TIME:
            self._finish()
        self.update()

    def _pose(self):
        """Текущий поворот (матрица) и высота над столом (0 — лежит)."""
        now = time.time()
        base = _face_to_top(self.value)

        if self.state == "roll":
            t = min(1.0, (now - self.t0) / ROLL_TIME)
            left = 1 - _ease_out(t)  # сколько вращения осталось
            sx, sy, sz = self.spin
            spin = _mul(_rot_x(2 * math.pi * sx * left),
                        _mul(_rot_y(2 * math.pi * sy * left), _rot_z(2 * math.pi * sz * left)))
            # сначала прыжок вверх, потом падение с отскоками
            if t < 0.25:
                height = AIR_HEIGHT * math.sin(t / 0.25 * math.pi / 2)
            else:
                height = AIR_HEIGHT * _bounce((t - 0.25) / 0.75)
            return _mul(VIEW, _mul(spin, base)), height

        if self.state == "air":
            t = now - self.t0
            spin = _mul(_rot_x(t * 3.1), _rot_y(t * 2.3))
            rise = min(1.0, t / 0.3)
            height = AIR_HEIGHT * rise + 0.06 * math.sin(t * 4)
            return _mul(VIEW, _mul(spin, base)), height

        if self.state == "land":
            t = min(1.0, (now - self.t0) / LAND_TIME)
            left = 1 - _ease_out(t)
            sx, sy, _ = self.spin
            spin = _mul(_rot_x(2 * math.pi * sx * left), _rot_y(2 * math.pi * sy * left))
            return _mul(VIEW, _mul(spin, base)), AIR_HEIGHT * _bounce(t)

        # спокойно лежит и чуть-чуть «дышит»
        breath = 0.025 * (1 + math.sin((now - self.t0) * 2.0))
        return _mul(VIEW, base), breath

    # ---------- рисование ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        unit = min(w, h) * 0.19
        ground = h * 0.82
        matrix, height = self._pose()
        cx, cy = w / 2, ground - unit * 1.5 - height * unit * 1.5

        # Тень на «столе»: чем выше кубик, тем она меньше и бледнее
        lift = max(0.0, min(1.0, height / AIR_HEIGHT))
        shadow = QRadialGradient(QPointF(w / 2, ground), unit * 1.6)
        shadow.setColorAt(0, QColor(0, 0, 0, int(120 - 70 * lift)))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QPointF(w / 2, ground), unit * (1.7 - 0.6 * lift), unit * (0.42 - 0.15 * lift))

        # Мягкое золотое свечение, когда кубик в движении
        if self.state != "idle":
            glow = QRadialGradient(QPointF(cx, cy), unit * 2.6)
            glow.setColorAt(0, QColor(232, 182, 76, 60))
            glow.setColorAt(1, QColor(232, 182, 76, 0))
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy), unit * 2.6, unit * 2.6)

        for face in self._faces(matrix, cx, cy, unit):
            r, g, b = face["color"]
            painter.setPen(QPen(QColor(70, 72, 98, 140), 1.2))
            painter.setBrush(QBrush(QColor(r, g, b)))
            painter.drawPath(_rounded_path(face["polygon"]))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(PIP_ONE if face["count"] == 1 else PIP_COLOR))
            for ring in face["pips"]:
                path = QPainterPath()
                path.moveTo(QPointF(*ring[0]))
                for point in ring[1:]:
                    path.lineTo(QPointF(*point))
                path.closeSubpath()
                painter.drawPath(path)

        painter.end()

    @staticmethod
    def _project(point, cx, cy, unit):
        x, y, z = point
        k = CAMERA / (CAMERA - z)
        return cx + x * k * unit, cy - y * k * unit

    def _faces(self, matrix, cx, cy, unit):
        length = math.sqrt(sum(v * v for v in LIGHT))
        light = tuple(v / length for v in LIGHT)
        result = []

        for normal, axis_a, axis_b, count in FACES:
            n3 = _apply(matrix, normal)
            a3 = _apply(matrix, axis_a)
            b3 = _apply(matrix, axis_b)

            to_camera = (-n3[0], -n3[1], CAMERA - n3[2])
            if sum(n * c for n, c in zip(n3, to_camera)) <= 0:
                continue

            corners = []
            for sa, sb in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
                corner = tuple(n3[i] + a3[i] * sa + b3[i] * sb for i in range(3))
                corners.append(self._project(corner, cx, cy, unit))

            shade = max(0.0, sum(n * l for n, l in zip(n3, light)))
            t = 0.25 + 0.75 * shade
            color = tuple(int(d + (l - d) * t) for d, l in zip(FACE_DARK, FACE_LIGHT))

            pip_size = 0.24 if count == 1 else 0.17
            pips = []
            for pa, pb in PIPS[count]:
                center = tuple(n3[i] + a3[i] * pa + b3[i] * pb for i in range(3))
                ring = []
                for step in range(14):
                    angle = 2 * math.pi * step / 14
                    point = tuple(
                        center[i] + (a3[i] * math.cos(angle) + b3[i] * math.sin(angle)) * pip_size
                        for i in range(3)
                    )
                    ring.append(self._project(point, cx, cy, unit))
                pips.append(ring)

            result.append({"polygon": corners, "color": color, "pips": pips,
                           "count": count, "depth": n3[2]})

        result.sort(key=lambda face: face["depth"])
        return result
