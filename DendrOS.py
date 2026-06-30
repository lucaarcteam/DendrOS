#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication
from dendros.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DendrOS")
    app.setOrganizationName("DendrOS")

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
