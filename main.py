import ctypes
import sys
import traceback
from datetime import datetime

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pipka.config import ASSETS_DIR, PROJECT_DIR
from pipka.database import ChatDatabase
from pipka.ui import MainWindow


def setup_log():
    """Без консоли (ярлык или .exe) ошибки некуда выводить, поэтому пишем их в файл."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log = open(PROJECT_DIR / "pipka_log.txt", "a", encoding="utf-8", buffering=1)
        log.write("\n--- запуск " + datetime.now().isoformat(timespec="seconds") + " ---\n")
        sys.stdout = log
        sys.stderr = log
    except OSError:
        pass


def main():
    setup_log()

    def log_exception(kind, value, trace):
        traceback.print_exception(kind, value, trace)

    sys.excepthook = log_exception

    # Чтобы в панели задач был значок ПИПКИ, а не значок Python
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "pipka.assistant.app"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("ПИПКА")
    app.setStyle("Fusion")

    icon_path = ASSETS_DIR / "pipka.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    db = ChatDatabase()
    window = MainWindow(db)
    window.show()
    result = app.exec()
    db.close()
    raise SystemExit(result)


if __name__ == "__main__":
    main()
