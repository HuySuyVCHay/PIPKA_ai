import html
import os
import re
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QObject, QPoint, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QFrame,
    QMessageBox,
    QSizePolicy,
    QCheckBox,
    QGridLayout,
    QInputDialog,
    QMenu,
)

try:
    import winsound
except ImportError:
    winsound = None

from pipka import ai, autostart, extras, files, gemini_client, keystore, settings
from pipka.commands import handle as handle_command, execute_confirmed
from pipka.config import PROJECT_DIR
from pipka.dice import DiceWidget
from pipka.stt import VoiceListener, libs_available
from pipka.tgbot import TelegramBot
from pipka.tts import Speaker

# ---------- Цвета: казино — чёрный стол, зелёное сукно, золото ----------
BG = "#0a0b0e"
PANEL = "#111318"
CARD = "#191c23"
BORDER = "#2a2d36"
FELT = "#0d2a21"
FELT_BORDER = "#1d4a3a"
TEXT = "#efe9da"
MUTED = "#8f8878"
GOLD = "#e8b64c"
GOLD_HOVER = "#f6cb6c"
GOLD_DARK = "#2b2414"
RED = "#e0484d"
GREEN = "#4fd18b"

STYLE = f"""
QMainWindow, QWidget {{
    background:{BG};
    color:{TEXT};
    font-family:'Segoe UI';
    font-size:10pt;
}}
QFrame#panel {{
    background:{PANEL};
    border:1px solid {BORDER};
    border-radius:18px;
}}
QFrame#table {{
    background:qradialgradient(cx:0.5, cy:0.35, radius:0.9, fx:0.5, fy:0.35,
                               stop:0 #12382b, stop:1 {FELT});
    border:2px solid {FELT_BORDER};
    border-radius:22px;
}}
QFrame#panel QLabel, QFrame#panel QCheckBox, QFrame#card QLabel,
QFrame#table QLabel, QFrame#chip QLabel {{ background:transparent; }}
QFrame#card {{
    background:{CARD};
    border:1px solid {BORDER};
    border-radius:12px;
}}
QFrame#chip {{
    background:{GOLD_DARK};
    border:1px solid {GOLD};
    border-radius:16px;
}}
QLabel#title {{ color:{GOLD}; font-size:20pt; font-weight:900; letter-spacing:3px; }}
QLabel#suits {{ color:{MUTED}; font-size:11pt; letter-spacing:6px; }}
QLabel#section {{ color:{GOLD}; font-size:8pt; font-weight:700; letter-spacing:2px; }}
QLabel#muted {{ color:{MUTED}; font-size:9pt; }}
QLabel#head {{ color:{TEXT}; font-size:14pt; font-weight:700; }}
QLabel#result {{ color:{GOLD}; font-size:11pt; font-weight:800; }}
QPushButton {{
    background:{CARD};
    color:{TEXT};
    border:1px solid {BORDER};
    border-radius:10px;
    padding:9px 12px;
    text-align:left;
}}
QPushButton:hover {{ border:1px solid {GOLD}; background:#20232c; }}
QPushButton:pressed {{ background:#262a34; }}
QPushButton:disabled {{ color:#555; }}
QPushButton#primary {{
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {GOLD_HOVER}, stop:1 {GOLD});
    color:#1b1405;
    border:0px;
    font-weight:800;
    text-align:center;
    padding:10px 20px;
}}
QPushButton#primary:hover {{ background:{GOLD_HOVER}; }}
QPushButton#primary:disabled {{ background:#5c5034; color:#2b2414; }}
QPushButton#round {{
    background:#0b1f18;
    border:1px solid {FELT_BORDER};
    border-radius:21px;
    min-width:42px; max-width:42px;
    min-height:42px; max-height:42px;
    padding:0px;
    text-align:center;
    font-size:14pt;
}}
QPushButton#round:hover {{ border:1px solid {GOLD}; }}
QPushButton#roll {{
    background:transparent;
    color:{GOLD};
    border:1px solid {GOLD};
    border-radius:15px;
    padding:6px 14px;
    text-align:center;
    font-weight:700;
}}
QPushButton#roll:hover {{ background:{GOLD_DARK}; }}
QPushButton#tile {{
    text-align:center;
    padding:12px 4px;
    font-size:9pt;
}}
QLineEdit {{
    background:#0b1f18;
    color:{TEXT};
    border:1px solid {FELT_BORDER};
    border-radius:21px;
    padding:10px 16px;
    min-height:20px;
}}
QLineEdit:focus {{ border:1px solid {GOLD}; }}
QTextEdit {{
    background:transparent;
    color:{TEXT};
    border:0px;
    padding:6px 10px;
}}
QCheckBox {{ spacing:10px; padding:4px 2px; color:{TEXT}; }}
QCheckBox::indicator {{
    width:34px; height:18px; border-radius:9px;
    background:#2a2d36; border:1px solid {BORDER};
}}
QCheckBox::indicator:checked {{ background:{GOLD}; border:1px solid {GOLD}; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:2px; }}
QScrollBar::handle:vertical {{ background:#2f5a49; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QMenu {{ background:{CARD}; color:{TEXT}; border:1px solid {GOLD}; padding:6px; }}
QMenu::item {{ padding:8px 18px; }}
QMenu::item:selected {{ background:{GOLD}; color:#1b1405; }}
QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 8px; }}
QMessageBox, QInputDialog {{ background:{PANEL}; }}
"""

PILL_ON = (f"QLabel{{padding:4px 12px;border-radius:11px;background:#123326;"
           f"color:{GREEN};border:1px solid #23573f;font-size:9pt;}}")
PILL_OFF = (f"QLabel{{padding:4px 12px;border-radius:11px;background:#0b1f18;"
            f"color:{MUTED};border:1px solid {FELT_BORDER};font-size:9pt;}}")
LISTEN_ON = (f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {GOLD_HOVER},stop:1 {GOLD});"
             "color:#1b1405;font-weight:800;border-radius:12px;padding:12px;text-align:center;border:0px;}"
             f"QPushButton:hover{{background:{GOLD_HOVER};}}")
LISTEN_OFF = (f"QPushButton{{background:{CARD};color:{MUTED};border:1px solid {BORDER};"
              "border-radius:12px;padding:12px;text-align:center;}"
              f"QPushButton:hover{{border:1px solid {GOLD};color:{TEXT};}}")
WELCOME_HTML = (
    f'<p align="center" style="margin-top:80px;color:{GOLD};font-size:26pt">♠ ♥ ♦ ♣</p>'
    f'<p align="center" style="color:{TEXT};font-size:20pt;font-weight:800">Делайте ваши ставки!</p>'
    f'<p align="center" style="color:{MUTED};font-size:11pt">Напиши сообщение или скажи «ПИПКА» — я на раздаче.</p>'
    f'<p align="center" style="color:{GOLD};font-size:10pt">«открой стим» · «открой папку папа» · «брось кубик» · «помощь»</p>'
)

QUICK_ACTIONS = [
    ("✈️\nTelegram", "открой телеграм"),
    ("▶️\nYouTube", "открой ютуб"),
    ("🎒\neMaktab", "открой emaktab"),
    ("🔎\nGoogle", "открой гугл"),
    ("🎮\nSteam", "открой стим"),
    ("⛏️\nMinecraft", "открой майнкрафт"),
    ("🧮\nКалькулятор", "открой калькулятор"),
    ("📝\nБлокнот", "открой блокнот"),
    ("📁\nПапки", "открой проводник"),
    ("🕒\nВремя", "который час"),
    ("🌦️\nПогода", "какая погода"),
    ("📸\nСкриншот", "сделай скриншот"),
    ("🔊\nГромче", "громче"),
    ("🔉\nТише", "тише"),
    ("⏯️\nПауза", "пауза"),
    ("🎡\nРулетка", "рулетка на красное"),
]

DICE_ROLL_RE = re.compile(
    r"^(?:пипка\s+)?(?:брось|кинь|подбрось|бросай|кидай|бросить|кинуть|крутани)\s+"
    r"(?:мне\s+)?(?:кубик|кубики|кость|кости)\b", re.IGNORECASE)
DICE_ASK_RE = re.compile(
    r"(?:что|сколько|какое число|какая цифра|какое)\s+(?:тебе\s+|у тебя\s+)?(?:выпало|на кубике)",
    re.IGNORECASE)

ROLL_LINES = {
    1: "Выпало 1. Змеиный глаз — не наш день, крутим ещё?",
    2: "Выпало 2. Скромненько, но фишки остаются при нас.",
    3: "Выпало 3. Середнячок — ставка сыграла вничью.",
    4: "Выпало 4. Неплохо, крупье доволен.",
    5: "Выпало 5. Удача рядом, чувствую запах джекпота!",
    6: "Выпало 6. Джекпот! Держи бонус: плюс 50 фишек.",
}
SIX_BONUS = 50


class Worker(QObject):
    chunk = Signal(str)
    success = Signal(str)
    failure = Signal(str)

    def __init__(self, messages, facts, extra):
        super().__init__()
        self.messages = messages
        self.facts = facts
        self.extra = extra

    def run(self):
        try:
            answer = ai.ask_stream(
                self.messages,
                lambda part: self.chunk.emit(part),
                self.facts,
                self.extra,
            )
            self.success.emit(answer)
        except Exception as exc:
            self.failure.emit(str(exc))


class VoiceBridge(QObject):
    status = Signal(str)
    heard = Signal(str)
    text = Signal(str)
    wake = Signal()
    error = Signal(str)
    stopped = Signal(int)
    tts_error = Signal(str)
    bot_event = Signal(str)
    command_done = Signal(object, object)
    reminder = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()

        self.db = db
        self.worker_thread = None
        self.worker = None
        self.streamed_answer = ""
        self.welcome_shown = False
        self.bot = None
        self.pending_prefix = ""
        self.report_roll = False
        self.command_busy = False

        self.bridge = VoiceBridge()
        self.bridge.status.connect(self.on_voice_status)
        self.bridge.heard.connect(self.on_voice_heard)
        self.bridge.text.connect(self.on_voice_text)
        self.bridge.wake.connect(self.on_voice_wake)
        self.bridge.error.connect(self.on_voice_error)
        self.bridge.stopped.connect(self.on_voice_stopped)
        self.bridge.tts_error.connect(self.on_voice_error)
        self.bridge.bot_event.connect(self.on_bot_event)
        self.bridge.command_done.connect(self.on_command_done)
        self.bridge.reminder.connect(self.on_reminder)
        extras.on_reminder = self.bridge.reminder.emit

        self.speaker = Speaker(on_error=self.bridge.tts_error.emit)
        self.listener = VoiceListener(
            on_status=self.bridge.status.emit,
            on_heard=self.bridge.heard.emit,
            on_text=self.bridge.text.emit,
            on_wake=self.bridge.wake.emit,
            on_error=self.bridge.error.emit,
            on_stopped=self.bridge.stopped.emit,
            is_muted=lambda: self.speaker.speaking,
        )

        self.setWindowTitle("ПИПКА")
        self.resize(1320, 820)
        self.setMinimumSize(1000, 680)
        self.setStyleSheet(STYLE)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        layout.addWidget(self._build_left())
        layout.addWidget(self._build_table(), 1)
        layout.addWidget(self._build_right())

        for message in self.db.recent(30):
            who = "Ты" if message["role"] == "user" else "ПИПКА"
            self.add_message(who, message["content"])
        if not self.db.recent(1):
            self.show_welcome()

        self.check_status()
        files.build_in_background()
        self.autostart_bot()
        self.autostart_wake()
        self.refresh_listen_button()
        self.refresh_pills()

        self.pill_timer = QTimer(self)
        self.pill_timer.timeout.connect(self.refresh_pills)
        self.pill_timer.start(1000)

    # ---------- построение окна ----------
    def _build_left(self):
        left = QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(250)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(18, 18, 18, 18)
        ll.setSpacing(8)

        title = QLabel("ПИПКА")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ll.addWidget(title)
        suits = QLabel(f'♠ <span style="color:{RED}">♥</span> <span style="color:{RED}">♦</span> ♣')
        suits.setObjectName("suits")
        suits.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ll.addWidget(suits)

        self.dice = DiceWidget()
        self.dice.rolled.connect(self.on_dice_rolled)
        ll.addWidget(self.dice, 0, Qt.AlignmentFlag.AlignHCenter)

        chip = QFrame()
        chip.setObjectName("chip")
        chip_row = QHBoxLayout(chip)
        chip_row.setContentsMargins(10, 7, 10, 7)
        self.dice_label = QLabel("🎲  Ставок нет")
        self.dice_label.setObjectName("result")
        chip_row.addWidget(self.dice_label, 1)
        self.chips_label = QLabel("")
        self.chips_label.setObjectName("result")
        self.chips_label.setToolTip("Твои фишки. Играй: «рулетка на красное 100 фишек», "
                                    "«ставлю на орла», за шестёрку на кубике +50.")
        chip_row.addWidget(self.chips_label)
        ll.addWidget(chip)

        roll_btn = QPushButton("Бросить кубик")
        roll_btn.setObjectName("roll")
        roll_btn.clicked.connect(lambda: self.roll_dice(report=True))
        ll.addWidget(roll_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        ll.addSpacing(6)

        voice_title = QLabel("ГОЛОС")
        voice_title.setObjectName("section")
        ll.addWidget(voice_title)

        self.wake_box = QPushButton()
        self.wake_box.setCheckable(True)
        self.wake_box.toggled.connect(self.toggle_wake)
        ll.addWidget(self.wake_box)

        voice_card = QFrame()
        voice_card.setObjectName("card")
        vc = QVBoxLayout(voice_card)
        vc.setContentsMargins(12, 10, 12, 10)
        self.voice_label = QLabel("Микрофон выключен.")
        self.voice_label.setObjectName("muted")
        self.voice_label.setWordWrap(True)
        vc.addWidget(self.voice_label)
        ll.addWidget(voice_card)

        ll.addSpacing(6)
        options_title = QLabel("ПАРАМЕТРЫ")
        options_title.setObjectName("section")
        ll.addWidget(options_title)

        self.voice_reply_box = QCheckBox("Озвучивать ответы")
        self.voice_reply_box.setChecked(True)
        ll.addWidget(self.voice_reply_box)

        self.bot_box = QCheckBox("Telegram-бот")
        self.bot_box.toggled.connect(self.toggle_bot)
        ll.addWidget(self.bot_box)

        ll.addStretch()

        self.settings_btn = QPushButton("⚙   Настройки")
        self.settings_btn.clicked.connect(self.open_settings)
        ll.addWidget(self.settings_btn)
        return left

    def _build_table(self):
        center = QFrame()
        center.setObjectName("table")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)

        head_row = QHBoxLayout()
        head = QLabel("♠  Стол")
        head.setObjectName("head")
        head_row.addWidget(head)
        head_row.addSpacing(10)
        self.pill_labels = {}
        for key in ["ai", "mic", "bot"]:
            label = QLabel("")
            self.pill_labels[key] = label
            head_row.addWidget(label)
        head_row.addStretch()
        cl.addLayout(head_row)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{FELT_BORDER};")
        cl.addWidget(line)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cl.addWidget(self.chat, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setObjectName("round")
        self.mic_btn.setToolTip("Сказать одну фразу")
        self.mic_btn.clicked.connect(self.toggle_mic)
        row.addWidget(self.mic_btn)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Твоя ставка: напиши сообщение или команду…")
        self.entry.returnPressed.connect(self.send)
        row.addWidget(self.entry, 1)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.send_btn)
        cl.addLayout(row)
        return center

    def _build_right(self):
        right = QFrame()
        right.setObjectName("panel")
        right.setFixedWidth(240)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 18, 16, 18)
        rl.setSpacing(10)

        quick_title = QLabel("♦  БЫСТРЫЕ ДЕЙСТВИЯ")
        quick_title.setObjectName("section")
        rl.addWidget(quick_title)

        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (label, command_text) in enumerate(QUICK_ACTIONS):
            button = QPushButton(label)
            button.setObjectName("tile")
            button.clicked.connect(lambda checked=False, c=command_text: self.quick(c))
            grid.addWidget(button, index // 2, index % 2)
        rl.addLayout(grid)
        rl.addStretch()

        status_card = QFrame()
        status_card.setObjectName("card")
        sc = QVBoxLayout(status_card)
        sc.setContentsMargins(12, 10, 12, 10)
        self.connection = QLabel("")
        self.connection.setWordWrap(True)
        sc.addWidget(self.connection)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        sc.addWidget(self.status)
        rl.addWidget(status_card)
        return right

    # ---------- чат ----------
    def _append_block(self, inner_html, align, top=0, fmt=None):
        """Новый абзац с явным выравниванием (иначе Qt берёт его у прошлого абзаца)."""
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        block = QTextBlockFormat()
        block.setAlignment(align)
        block.setTopMargin(top)
        if not self.chat.document().isEmpty():
            cursor.insertBlock(block, fmt or QTextCharFormat())
        if inner_html:
            cursor.insertHtml(inner_html)
        cursor.setBlockFormat(block)
        if fmt is not None:
            cursor.setCharFormat(fmt)
        self.chat.setTextCursor(cursor)
        return cursor

    def _header(self, who, stamp):
        if who == "ПИПКА":
            return (f'<span style="color:{GOLD};font-weight:800">🎲 ПИПКА</span>'
                    f'&nbsp;&nbsp;<span style="color:#5f8a78;font-size:8pt">{stamp}</span>')
        return (f'<span style="color:#5f8a78;font-size:8pt">{stamp}</span>&nbsp;&nbsp;'
                f'<span style="color:{MUTED};font-weight:700">{html.escape(who)} ♣</span>')

    def add_message(self, who, text):
        self._clear_welcome()
        safe_text = html.escape(str(text)).replace("\n", "<br>")
        stamp = datetime.now().strftime("%H:%M")
        mine = who != "ПИПКА"
        align = Qt.AlignmentFlag.AlignRight if mine else Qt.AlignmentFlag.AlignLeft
        color = "#d8f0e4" if mine else TEXT
        self._append_block(self._header(who, stamp), align, top=16)
        self._append_block(f'<span style="color:{color}">{safe_text}</span>', align, top=4)
        self.chat.ensureCursorVisible()

    def add_note(self, text):
        self._clear_welcome()
        self._append_block(
            f'<span style="color:#7fa898;font-size:9pt">{html.escape(str(text))}</span>',
            Qt.AlignmentFlag.AlignHCenter, top=10,
        )
        self.chat.ensureCursorVisible()

    def reply(self, text, user_text=None):
        """Ответ ПИПКИ в чат, в историю и голосом."""
        if user_text is not None:
            self.db.add("user", user_text)
        self.db.add("assistant", text)
        self.add_message("ПИПКА", text)
        self.speak(text)

    def _begin_stream(self):
        self._clear_welcome()
        stamp = datetime.now().strftime("%H:%M")
        self._append_block(self._header("ПИПКА", stamp), Qt.AlignmentFlag.AlignLeft, top=16)
        self._stream_format = QTextCharFormat()
        self._stream_format.setForeground(QColor(TEXT))
        self._stream_format.setFontWeight(400)
        self._append_block("", Qt.AlignmentFlag.AlignLeft, top=4, fmt=self._stream_format)

    def show_welcome(self):
        self.welcome_shown = True
        self.chat.setHtml(WELCOME_HTML)

    def _clear_welcome(self):
        if self.welcome_shown:
            self.welcome_shown = False
            self.chat.clear()

    # ---------- статусы ----------
    def set_pill(self, key, text, on):
        label = self.pill_labels.get(key)
        if label is not None:
            label.setText(text)
            label.setStyleSheet(PILL_ON if on else PILL_OFF)

    def refresh_pills(self):
        has_key = ai.has_key()
        self.set_pill("ai", "ИИ: Gemini" if has_key else "ИИ: нет ключа", has_key)
        listening = bool(self.listener.running)
        self.set_pill("mic", "Слушает «ПИПКА»" if listening else "Микрофон выкл", listening)
        bot_on = self.bot is not None
        self.set_pill("bot", "Telegram: вкл" if bot_on else "Telegram: выкл", bot_on)
        self.chips_label.setText(f"♦ {extras.chips()}")

    def refresh_listen_button(self):
        on = bool(self.wake_box.isChecked())
        self.wake_box.setText("●  Слушаю «ПИПКА»" if on else "○  Включить слушание")
        self.wake_box.setStyleSheet(LISTEN_ON if on else LISTEN_OFF)

    def check_status(self):
        if ai.has_key():
            self.connection.setText("♠ Gemini: ключ на месте")
            self.connection.setStyleSheet(f"color:{GREEN};font-size:9pt")
            self.status.setText("Команды работают без ИИ, вопросы — через Gemini.")
        else:
            self.connection.setText("♥ Gemini: нет ключа")
            self.connection.setStyleSheet(f"color:{RED};font-size:9pt")
            self.status.setText("Команды работают и так. Чтобы отвечать на вопросы, "
                                "добавь ключ: ⚙ Настройки.")

    def speak(self, text):
        if self.voice_reply_box.isChecked():
            self.speaker.say(text)

    # ---------- отправка ----------
    def send(self):
        text = self.entry.text().strip()
        if not text or self.worker_thread is not None:
            return
        self.entry.clear()
        self.submit(text)

    def busy(self):
        return self.worker_thread is not None or self.command_busy

    def submit(self, text):
        text = text.strip()
        if not text or self.busy():
            return
        self.speaker.stop()
        self.add_message("Ты", text)

        prefix, self.pending_prefix = self.pending_prefix, ""
        command_text = text
        if prefix and not text.lower().startswith(prefix):
            command_text = prefix + " " + text

        if DICE_ROLL_RE.search(command_text):
            self.db.add("user", text)
            self.roll_dice(report=True)
            return True
        if DICE_ASK_RE.search(command_text):
            self.reply(self.dice_text(), user_text=text)
            return True

        self.run_command(command_text, text)
        return True

    def run_command(self, command_text, user_text):
        """Команда выполняется в фоне (поиск файлов, погода, Gemini), окно не подвисает.
        user_text=None — это быстрая кнопка: ответ показывается заметкой."""
        self.command_busy = True
        self.send_btn.setEnabled(False)
        self.status.setText("ПИПКА крутит барабан…")

        def work():
            try:
                result = handle_command(command_text, db=self.db)
            except Exception as exc:
                result = exc
            self.bridge.command_done.emit(result, user_text)

        threading.Thread(target=work, daemon=True).start()

    def on_command_done(self, result, user_text):
        self.command_busy = False
        self.send_btn.setEnabled(True)
        self.check_status()

        if isinstance(result, Exception):
            self.add_note(f"Ошибка команды: {result}")
            return
        if user_text is None:
            if result.handled:
                self.add_note(result.message)
                self.send_photo(result.photo)
            return
        if result.handled:
            self.reply(result.message, user_text=user_text)
            self.send_photo(result.photo)
            if result.follow_up:
                self.pending_prefix = result.follow_up
                self.listener.expect_command(12)
            if result.confirm:
                self.ask_confirm(result)
            return
        self.start_ai(user_text)

    def start_ai(self, text):
        if not ai.has_key():
            self.reply(ai.NO_KEY, user_text=text)
            return

        self.db.add("user", text)
        self.streamed_answer = ""
        self.send_btn.setEnabled(False)
        self.entry.setEnabled(False)
        self.status.setText("ПИПКА думает…")
        self.dice.set_thinking(True)
        self._begin_stream()

        extra = (f"Сейчас на твоём игральном кубике (он на экране слева) выпало {self.dice.value}. "
                 f"У пользователя {extras.chips()} игровых фишек (понарошку, без денег).")
        self.worker_thread = QThread(self)
        self.worker = Worker(self.db.recent(20), self.db.facts(), extra)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.chunk.connect(self.show_chunk)
        self.worker.success.connect(self.answer)
        self.worker.failure.connect(self.error)
        self.worker.success.connect(self.worker_thread.quit)
        self.worker.failure.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.finished)
        self.worker_thread.start()

    def show_chunk(self, part):
        self.streamed_answer += part
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(part, self._stream_format)
        self.chat.ensureCursorVisible()

    def answer(self, text):
        self.db.add("assistant", text)
        self.check_status()
        self.dice.set_thinking(False)
        self.speak(text)

    def error(self, message):
        self.db.remove_last_if_user()
        prefix = "\n" if self.streamed_answer else ""
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(prefix + "Не получилось ответить: " + message, self._stream_format)
        self.status.setText("Проверь интернет и ключ Gemini.")
        self.dice.set_thinking(False)

    def finished(self):
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self.send_btn.setEnabled(True)
        self.entry.setEnabled(True)
        self.entry.setFocus()

    # ---------- подтверждения ----------
    def perform_confirmed(self, key):
        if key in ("shutdown", "restart"):
            return execute_confirmed(key)
        if key == "forget_facts":
            self.db.clear_facts()
            return True, "Готово, я всё забыла."
        if key == "clear_history":
            self.db.clear_messages()
            self.chat.clear()
            self.show_welcome()
            return True, "История чата очищена."
        return False, "Неизвестное действие."

    def ask_confirm(self, command):
        answer = QMessageBox.question(
            self, "Подтверждение", command.confirm_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            ok, message = self.perform_confirmed(command.confirm)
        else:
            ok, message = True, "Хорошо, ничего не трогаю."
        self.add_message("ПИПКА", message)
        if not ok:
            QMessageBox.warning(self, "Ошибка", message)

    # ---------- кубик ----------
    def dice_text(self):
        if self.dice.state != "idle":
            return "Кубик ещё катится, секунду…"
        return f"Сейчас на кубике {self.dice.value}."

    def roll_dice(self, report=False):
        self.report_roll = report or self.report_roll
        self.dice.interact()

    def on_dice_rolled(self, number):
        labels = {1: "🎲 1 · змеиный глаз", 6: "🎲 6 · ДЖЕКПОТ!"}
        self.dice_label.setText(labels.get(number, f"🎲 Выпало {number}"))
        if number == 6:
            extras.change_chips(SIX_BONUS)
            self.chips_label.setText(f"♦ {extras.chips()}")
        if self.report_roll:
            self.report_roll = False
            self.reply(ROLL_LINES[number])

    # ---------- голос ----------
    def toggle_mic(self):
        if self.listener.running:
            self.listener.stop()
            return
        self.dice.interact()
        self.mic_btn.setText("⏹")
        if not self.listener.start("once"):
            self.mic_btn.setText("🎤")

    def toggle_wake(self, checked):
        if checked:
            self.dice.interact()
            self.mic_btn.setText("⏹")
            if not self.listener.start("wake"):
                self.wake_box.blockSignals(True)
                self.wake_box.setChecked(False)
                self.wake_box.blockSignals(False)
                self.refresh_listen_button()
                return
            settings.save({"wake_on_start": True})
        else:
            settings.save({"wake_on_start": False})
            self.listener.stop()
        self.refresh_listen_button()

    def autostart_wake(self):
        if not settings.get("wake_on_start"):
            return
        if not libs_available()[0]:
            self.add_note("Слушание не включилось: нет библиотек голоса (vosk, sounddevice).")
            return
        self.wake_box.blockSignals(True)
        self.wake_box.setChecked(True)
        self.wake_box.blockSignals(False)
        self.toggle_wake(True)

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def on_voice_status(self, text):
        self.voice_label.setText(text)

    def on_voice_heard(self, text):
        self.voice_label.setText("Слышу: " + text)
        print(datetime.now().strftime("%H:%M:%S"), "слышу:", text, flush=True)

    def on_voice_text(self, text):
        if self.busy():
            self.voice_label.setText("Подожди, я ещё отвечаю.")
            return
        self.voice_label.setText("Команда: " + text)
        self.submit(text)

    def on_voice_wake(self):
        self.dice.interact()
        self.bring_to_front()
        self.voice_label.setText("Слушаю тебя…")
        if winsound is not None:
            try:
                winsound.Beep(880, 120)
            except RuntimeError:
                pass

    def on_voice_error(self, message):
        print(datetime.now().strftime("%H:%M:%S"), "ошибка голоса:", message, flush=True)
        self.voice_label.setText(message)
        self.add_note(message)

    def on_voice_stopped(self, session):
        if session != self.listener.session:
            return
        self.mic_btn.setText("🎤")
        self.wake_box.blockSignals(True)
        self.wake_box.setChecked(False)
        self.wake_box.blockSignals(False)
        self.refresh_listen_button()

    # ---------- Telegram ----------
    def autostart_bot(self):
        if settings.get("bot_on_start") and keystore.get_telegram_token():
            self.bot_box.setChecked(True)

    def on_bot_event(self, message):
        print(datetime.now().strftime("%H:%M:%S"), "бот:", message, flush=True)
        self.add_note(message)

    def toggle_bot(self, checked):
        if checked:
            if not keystore.get_telegram_token() and not self.ask_telegram_token():
                self.bot_box.blockSignals(True)
                self.bot_box.setChecked(False)
                self.bot_box.blockSignals(False)
                return
            settings.save({"bot_on_start": True})
            if self.bot is not None:
                self.bot.stop()
            try:
                self.bot = TelegramBot(on_event=self.bridge.bot_event.emit)
                self.bot.start()
            except Exception as exc:
                self.bot = None
                self.add_note(f"Ошибка бота: {exc}")
                self.bot_box.blockSignals(True)
                self.bot_box.setChecked(False)
                self.bot_box.blockSignals(False)
        else:
            settings.save({"bot_on_start": False})
            if self.bot is not None:
                self.bot.stop()
                self.bot = None
            self.add_note("Telegram-бот остановлен.")

    # ---------- быстрые кнопки ----------
    def quick(self, command_text):
        if self.busy():
            return
        self.dice.interact()
        self.run_command(command_text, None)

    # ---------- напоминания и Telegram ----------
    def on_reminder(self, text):
        self.bring_to_front()
        if winsound is not None:
            for _ in range(3):
                try:
                    winsound.Beep(988, 180)
                    winsound.Beep(1319, 220)
                except RuntimeError:
                    break
        self.reply("⏰ " + text)
        self.dice.interact()
        self.notify_phone("⏰ " + text)

    def notify_phone(self, text):
        bot = self.bot
        if bot is not None and bot.owner is not None:
            threading.Thread(target=bot.send, args=(bot.owner, text), daemon=True).start()

    def send_photo(self, path):
        bot = self.bot
        if path and bot is not None and bot.owner is not None:
            threading.Thread(target=bot.send_photo, args=(bot.owner, path), daemon=True).start()
            self.add_note("Отправила скриншот в Telegram.")

    # ---------- настройки ----------
    def open_settings(self):
        menu = QMenu(self)
        has_key = ai.has_key()
        menu.addAction("🔑  Изменить ключ Gemini" if has_key else "🔑  Ввести ключ Gemini",
                       self.ask_gemini_key)
        if has_key:
            menu.addAction("🗑  Удалить ключ Gemini", self.remove_gemini_key)
        menu.addSeparator()
        auto = menu.addAction("🚀  Запускать вместе с Windows")
        auto.setCheckable(True)
        auto.setChecked(autostart.is_enabled())
        auto.toggled.connect(self.set_autostart)
        menu.addSeparator()
        menu.addAction("✈️  Токен Telegram-бота", self.ask_telegram_token)
        if keystore.get_telegram_owner():
            menu.addAction("📱  Отвязать телефон", self.unpair_phone)
        menu.addSeparator()
        menu.addAction("🔄  Обновить список файлов", self.refresh_files)
        menu.addAction("📂  Открыть папку с данными", self.open_data_folder)
        menu.exec(self.settings_btn.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 6)))

    def ask_gemini_key(self):
        key, ok = QInputDialog.getText(
            self, "Ключ Gemini",
            "Вставь ключ с сайта aistudio.google.com (Get API key):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not key.strip():
            return
        saved, message = keystore.save_gemini_key(key)
        gemini_client.reset_model_cache()
        self.add_note(message)
        self.check_status()
        self.refresh_pills()
        if not saved:
            QMessageBox.warning(self, "Ключ Gemini", message)

    def remove_gemini_key(self):
        ok, message = keystore.delete_gemini_key()
        gemini_client.reset_model_cache()
        self.add_note(message)
        self.check_status()
        self.refresh_pills()

    def set_autostart(self, on):
        ok, message = autostart.enable() if on else autostart.disable()
        self.add_note(message)

    def ask_telegram_token(self):
        token, ok = QInputDialog.getText(
            self, "Telegram-бот",
            "Токен бота от @BotFather (никому его не показывай):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not token.strip():
            return False
        saved, message = keystore.save_telegram_token(token)
        self.add_note(message)
        if not saved:
            QMessageBox.warning(self, "Telegram-бот", message)
        elif self.bot is not None:
            self.bot.stop()
            self.bot = TelegramBot(on_event=self.bridge.bot_event.emit)
            self.bot.start()
        return saved

    def unpair_phone(self):
        keystore.clear_telegram_owner()
        self.add_note("Телефон отвязан. Выключи и включи Telegram-бот, чтобы привязать снова.")

    def refresh_files(self):
        files.build_in_background()
        self.add_note("Обновляю список файлов и папок…")

    def open_data_folder(self):
        try:
            os.startfile(str(PROJECT_DIR))
        except OSError as exc:
            self.add_note(f"Не получилось открыть папку: {exc}")
