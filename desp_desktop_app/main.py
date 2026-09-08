#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.theme import configure_application, configure_high_dpi


def main() -> int:
    configure_high_dpi()
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
