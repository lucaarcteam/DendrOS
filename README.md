# DendrOS

**Dendrochronology Software** — cross-platform (Windows/Linux).

DendrOS is an open‑source application for dendrochronological analysis and cross‑dating of tree‑ring width series. It provides a modern graphical interface for managing, visualizing, and statistically comparing dendro data.

Developed in scientific collaboration with:
- **Mauro Bernabei** — CNR‑IBE (Institute of BioEconomy, National Research Council of Italy)
- **Luca Bezzi** — Arc‑Team

Licensed under **GNU General Public License v3**.

## Features

- Import `.rwl`, `.txt`, and `.fh` (CATRAS/Holmes‑format) files
- Interactive time‑series plot with pan, zoom, year cursor, and log‑scale Y
- Series tree with View/Edit/Ref/Info columns for managing multiple series
- **Cross‑dating** (Baillie‑Pilcher tBP with p‑values, Pearson r, Gleichläufigkeit)
- **Master chronology** builder (averaging overlap)
- **Concordance bands** for pairwise comparison
- **Detrending / Indexing** via dplPy (spline, ModNegex, Hugershoff, linear, horizontal)
- **Pointer years** (Weiserjahre) visual markers
- Project save/load (`.dendro` format)
- Windows standalone executable via PyInstaller + Docker

## Requirements

- Python 3.12+
- PyQt6, numpy, matplotlib, scipy, pandas, dplPy

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python DendrOS.py
```

## Windows build

```bash
./build_win_exe.sh
```

Output: `dist/windows/DendrOS.exe`

## Repository

https://github.com/lucaarcteam/DendrOS
