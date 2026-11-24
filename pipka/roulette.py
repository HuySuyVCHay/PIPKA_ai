"""Окно рулетки: колесо крутится и останавливается на числе, ставки фишками (понарошку)."""

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pipka import extras
from pipka.system import FONT, beep

# Порядок чисел на европейском колесе (по часовой стрелке)
WHEEL = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24,
         16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
SPIN_TIME = 4.5
GOLD = QColor("#e8b64c")
RED = QColor("#c8323a")
BLACK = QColor("#15171c")
GREEN = QColor("#1f8f4e")

STYLE = """
QDialog { background:#0a0b0e; color:#efe9da; font-family:'FONTNAME'; font-size:10pt; }
QLabel { background:transparent; color:#efe9da; }
QLabel#title { color:#e8b64c; font-size:18pt; font-weight:900; letter-spacing:2px; }
QLabel#section { color:#e8b64c; font-size:8pt; font-weight:700; letter-spacing:2px; }
QLabel#balance { color:#e8b64c; font-size:15pt; font-weight:800; }
QLabel#result { font-size:12pt; font-weight:700; }
QLabel#muted { color:#8f8878; font-size:9pt; }
QPushButton {
    background:#191c23; color:#efe9da; border:1px solid #2a2d36;
    border-radius:10px; padding:9px 6px;
}
QPushButton:hover { border:1px solid #e8b64c; }
QPushButton:checked { background:#2b2414; border:2px solid #e8b64c; color:#f6cb6c; font-weight:700; }
QPushButton#red { background:#5a171b; }
QPushButton#red:checked { background:#8f2128; color:white; }
QPushButton#black { background:#15171c; }
QPushButton#green { background:#11452a; }
QPushButton#green:checked { background:#1f8f4e; color:white; }
QPushButton#chip { border-radius:20px; min-width:40px; min-height:40px; max-height:40px; font-weight:700; }
QPushButton#spin {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f6cb6c, stop:1 #e8b64c);
    color:#1b1405; border:0; font-size:13pt; font-weight:900; padding:12px; letter-spacing:2px;
}
QPushButton#spin:disabled { background:#5c5034; color:#2b2414; }
QSpinBox { background:#191c23; color:#efe9da; border:1px solid #2a2d36; border-radius:8px; padding:6px; }
""".replace("FONTNAME", FONT)


def _pocket_color(number):
    if number == 0:
        return GREEN
    return RED if number in extras.RED_NUMBERS else BLACK


def _ease_out(t):
    return 1 - (1 - t) ** 4


class WheelWidget(QWidget):
    """Колесо рулетки. spin_to(число) — крутится и останавливается на нём под стрелкой."""

    stopped = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 380)
        self.angle = 0.0
        self.result = None
        self.start_angle = 0.0
        self.target_angle = 0.0
        self.t0 = 0.0
        self.spinning = False
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def spin_to(self, number):
        step = 360 / len(WHEEL)
        index = WHEEL.index(number)
        # Карман с числом должен оказаться наверху, под золотой стрелкой
        final = -(index * step) + random.uniform(-step * 0.3, step * 0.3)
        turns = random.randint(5, 7) * 360
        self.start_angle = self.angle
        self.target_angle = final - turns
        while self.target_angle > self.start_angle - turns:
            self.target_angle -= 360
        self.result = number
        self.t0 = time.time()
        self.spinning = True
        self.timer.start()

    def tick(self):
        t = min(1.0, (time.time() - self.t0) / SPIN_TIME)
        self.angle = self.start_angle + (self.target_angle - self.start_angle) * _ease_out(t)
        if t >= 1.0:
            self.timer.stop()
            self.spinning = False
            self.angle %= 360
            self.stopped.emit(self.result)
        self.update()

    def pocket_at_top(self):
        step = 360 / len(WHEEL)
        index = round(-self.angle / step) % len(WHEEL)
        return WHEEL[index]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        size = min(w, h) - 20
        cx, cy = w / 2, h / 2 + 8
        outer = size / 2
        step = 360 / len(WHEEL)

        glow = QRadialGradient(QPointF(cx, cy), outer * 1.15)
        glow.setColorAt(0.8, QColor(232, 182, 76, 70 if self.spinning else 30))
        glow.setColorAt(1, QColor(232, 182, 76, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), outer * 1.15, outer * 1.15)

        painter.setBrush(QColor("#3a2a10"))
        painter.setPen(QPen(GOLD, 3))
        painter.drawEllipse(QPointF(cx, cy), outer, outer)

        ring_out = outer * 0.93
        ring_in = outer * 0.62
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)
        font = QFont(FONT, max(7, int(outer / 22)))
        font.setBold(True)
        painter.setFont(font)
        for i, number in enumerate(WHEEL):
            start = -90 - step / 2 + i * step
            path = QPainterPath()
            path.arcMoveTo(QRectF(-ring_out, -ring_out, ring_out * 2, ring_out * 2), -start)
            path.arcTo(QRectF(-ring_out, -ring_out, ring_out * 2, ring_out * 2), -start, -step)
            path.arcTo(QRectF(-ring_in, -ring_in, ring_in * 2, ring_in * 2), -start - step, step)
            path.closeSubpath()
            painter.setPen(QPen(QColor(232, 182, 76, 160), 1))
            painter.setBrush(_pocket_color(number))
            painter.drawPath(path)

            middle = math.radians(start + step / 2)
            radius = (ring_out + ring_in) / 2 + outer * 0.07
            painter.save()
            painter.translate(radius * math.cos(middle), radius * math.sin(middle))
            painter.rotate(start + step / 2 + 90)
            painter.setPen(QColor("white"))
            painter.drawText(QRectF(-14, -10, 28, 20), Qt.AlignmentFlag.AlignCenter, str(number))
            painter.restore()

        center = QRadialGradient(QPointF(0, 0), ring_in)
        center.setColorAt(0, QColor("#5a4320"))
        center.setColorAt(1, QColor("#22180a"))
        painter.setBrush(QBrush(center))
        painter.setPen(QPen(GOLD, 2))
        painter.drawEllipse(QPointF(0, 0), ring_in, ring_in)
        for k in range(4):
            painter.save()
            painter.rotate(k * 90)
            pen = QPen(GOLD, 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(0, -ring_in * 0.15), QPointF(0, -ring_in * 0.7))
            painter.restore()
        painter.setBrush(GOLD)
        painter.drawEllipse(QPointF(0, 0), ring_in * 0.14, ring_in * 0.14)
        painter.restore()

        # Шарик лежит в кармане под стрелкой
        ball_r = outer * 0.045
        ball_y = cy - ring_in - ball_r * 1.6
        if self.spinning:
            t = min(1.0, (time.time() - self.t0) / SPIN_TIME)
            wobble = (1 - t) * outer * 0.12 * abs(math.sin(t * 40))
            ball_y -= wobble
        painter.setPen(QPen(QColor("#999"), 1))
        painter.setBrush(QColor("#f4f4f4"))
        painter.drawEllipse(QPointF(cx, ball_y), ball_r, ball_r)

        arrow = QPainterPath()
        top = cy - outer - 4
        arrow.moveTo(cx - 12, top - 14)
        arrow.lineTo(cx + 12, top - 14)
        arrow.lineTo(cx, top + 10)
        arrow.closeSubpath()
        painter.setPen(QPen(QColor("#1b1405"), 1))
        painter.setBrush(GOLD)
        painter.drawPath(arrow)
        painter.end()


class RouletteDialog(QDialog):
    """Ставка: сколько фишек и на что. Кнопка «Крутить» — колесо решает."""

    played = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ПИПКА — рулетка")
        self.setStyleSheet(STYLE)
        self.resize(900, 560)
        self.bet = 100
        self.pick = "red"
        self.history = []

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)

        left = QVBoxLayout()
        title = QLabel("🎡  РУЛЕТКА")
        title.setObjectName("title")
        left.addWidget(title)
        self.wheel = WheelWidget()
        self.wheel.stopped.connect(self.on_stopped)
        left.addWidget(self.wheel, 1)
        self.result_label = QLabel("Делай ставку и крути!")
        self.result_label.setObjectName("result")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setWordWrap(True)
        left.addWidget(self.result_label)
        self.history_label = QLabel("")
        self.history_label.setObjectName("muted")
        self.history_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.history_label)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(10)
        self.balance_label = QLabel()
        self.balance_label.setObjectName("balance")
        right.addWidget(self.balance_label)

        right.addWidget(self._section("СТАВКА (ФИШКИ)"))
        chips_row = QHBoxLayout()
        self.chip_group = QButtonGroup(self)
        for amount in (10, 50, 100, 250, 500):
            button = QPushButton(str(amount))
            button.setObjectName("chip")
            button.setCheckable(True)
            button.setChecked(amount == self.bet)
            button.clicked.connect(lambda checked=False, a=amount: self.set_bet(a))
            self.chip_group.addButton(button)
            chips_row.addWidget(button)
        all_in = QPushButton("Всё")
        all_in.setObjectName("chip")
        all_in.setCheckable(True)
        all_in.clicked.connect(lambda: self.set_bet(None))
        self.chip_group.addButton(all_in)
        chips_row.addWidget(all_in)
        right.addLayout(chips_row)

        right.addWidget(self._section("НА ЧТО СТАВИМ"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.pick_group = QButtonGroup(self)
        options = [
            ("red", "Красное  ×2", "red"), ("black", "Чёрное  ×2", "black"),
            ("even", "Чётное  ×2", ""), ("odd", "Нечётное  ×2", ""),
            ("low", "1–18  ×2", ""), ("high", "19–36  ×2", ""),
            ("zero", "Зеро  ×36", "green"), ("number", "Число  ×36", ""),
        ]
        for index, (key, text, style) in enumerate(options):
            button = QPushButton(text)
            if style:
                button.setObjectName(style)
            button.setCheckable(True)
            button.setChecked(key == self.pick)
            button.clicked.connect(lambda checked=False, k=key: self.set_pick(k))
            self.pick_group.addButton(button)
            grid.addWidget(button, index // 2, index % 2)
        right.addLayout(grid)

        number_row = QHBoxLayout()
        number_row.addWidget(QLabel("Число:"))
        self.number_box = QSpinBox()
        self.number_box.setRange(1, 36)
        self.number_box.setValue(17)
        self.number_box.valueChanged.connect(lambda: self.set_pick("number"))
        number_row.addWidget(self.number_box, 1)
        right.addLayout(number_row)

        self.bet_label = QLabel()
        self.bet_label.setObjectName("muted")
        self.bet_label.setWordWrap(True)
        right.addWidget(self.bet_label)
        right.addStretch()

        self.spin_button = QPushButton("КРУТИТЬ")
        self.spin_button.setObjectName("spin")
        self.spin_button.clicked.connect(self.spin)
        right.addWidget(self.spin_button)

        rules = QLabel("Цвет, чёт/нечет и половины платят ×2, число и зеро — ×36. "
                       "На зеро все ставки кроме «Зеро» проигрывают. Фишки понарошку.")
        rules.setObjectName("muted")
        rules.setWordWrap(True)
        right.addWidget(rules)
        root.addLayout(right, 2)

        self.refresh()

    @staticmethod
    def _section(text):
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def set_bet(self, amount):
        self.bet = amount
        self.refresh()

    def set_pick(self, key):
        self.pick = key
        for button in self.pick_group.buttons():
            if key == "number" and button.text().startswith("Число"):
                button.setChecked(True)
        self.refresh()

    def current_bet(self):
        balance = extras.chips()
        return balance if self.bet is None else min(self.bet, balance)

    def current_pick(self):
        if self.pick == "zero":
            return "number", 0
        if self.pick == "number":
            return "number", self.number_box.value()
        return self.pick, None

    def refresh(self):
        self.balance_label.setText(f"♦ {extras.chips()} фишек")
        pick, number = self.current_pick()
        self.bet_label.setText(f"Ставка: {self.current_bet()} фишек на "
                               f"{extras.roulette_label(pick, number)}.")

    def spin(self):
        if self.wheel.spinning:
            return
        bonus = extras.ensure_chips()
        if bonus:
            self.result_label.setText(bonus.strip())
        self.spin_button.setEnabled(False)
        self.wheel.spin_to(random.randint(0, 36))

    def on_stopped(self, spin):
        pick, number = self.current_pick()
        bet = self.current_bet()
        win, payout, balance = extras.roulette_settle(spin, pick, bet, number)
        color = extras.roulette_color(spin)
        color_html = {"красное": "#ff5a62", "чёрное": "#efe9da", "зеро": "#4fd18b"}[color]
        verdict = (f'<span style="color:#4fd18b">ВЫИГРЫШ +{payout}!</span>' if win
                   else f'<span style="color:#ff5a62">ставка {bet} сгорела</span>')
        self.result_label.setText(f'<span style="color:{color_html}">{spin} ({color})</span> — {verdict}')
        self.history.insert(0, f'<span style="color:{color_html}">{spin}</span>')
        self.history = self.history[:12]
        self.history_label.setText("Последние: " + "  ".join(self.history))
        self.spin_button.setEnabled(True)
        self.refresh()
        if win:
            for tone in (880, 1109, 1319, 1760):
                beep(tone, 90)
        text = (f"Рулетка: {spin} ({color}). Ставка {bet} на {extras.roulette_label(pick, number)} — "
                + (f"выигрыш {payout}!" if win else "мимо.") + f" Фишек: {balance}.")
        self.played.emit(text)
