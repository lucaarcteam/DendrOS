#!/usr/bin/env python3
# DendrOS — Dendrochronology Software
# Copyright (C) 2026  Mauro Bernabei (CNR-IBE), Luca Bezzi (Arc-Team)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
