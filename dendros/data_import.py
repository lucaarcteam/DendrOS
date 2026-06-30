import os
import re
from typing import Optional
import numpy as np
from .models.series import Series


def _read_lines(filepath: str) -> list[str]:
    with open(filepath, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x85", "\n")
    return text.splitlines(keepends=True)


def read_fh(filepath: str, remove_year_zero: bool = False, start_at_one: bool = False) -> list[Series]:
    lines = _read_lines(filepath)
    if not lines:
        return []

    header_starts = [i for i, l in enumerate(lines) if l.rstrip() == "HEADER:"]
    data_starts = [i for i, l in enumerate(lines) if l.startswith("DATA:Tree") or l.startswith("DATA:Single") or l.startswith("DATA:Chrono")]
    n = len(data_starts)
    if n == 0:
        raise ValueError('file has no data in "Tree" or "Single" formats')

    header_taken = [False] * len(header_starts)
    for i in range(n):
        preceding = sum(1 for h in header_starts if h < data_starts[i] - 1)
        if preceding == 0 or header_taken[preceding - 1]:
            raise ValueError("invalid file: HEADER and DATA don't match")
        header_taken[preceding - 1] = True

    data_ends = []
    for i in range(n):
        candidates = [h for h in header_starts if h > data_starts[i]]
        data_ends.append(candidates[0] if candidates else len(lines))

    header_starts = [h for h, taken in zip(header_starts, header_taken) if taken]

    result = []
    for i in range(n):
        header_lines = lines[header_starts[i] + 1 : data_starts[i]]

        def get_header(key: str) -> Optional[str]:
            pat = re.compile(rf"^{key}=", re.IGNORECASE)
            for hl in header_lines:
                if pat.match(hl):
                    return hl.split("=", 1)[1].strip()
            return None

        keycode = get_header("KeyCode")
        if not keycode:
            raise ValueError(f"series block {i+1}: missing KeyCode")
        length_str = get_header("Length")
        if not length_str:
            raise ValueError(f"series {keycode}: missing Length")
        length = int(length_str)
        date_end_str = get_header("DateEnd")
        date_begin_str = get_header("DateBegin")
        if date_end_str and date_begin_str:
            end_year = int(date_end_str)
            start_year = int(date_begin_str)
        elif date_end_str:
            end_year = int(date_end_str)
            start_year = end_year - length + 1
        elif date_begin_str:
            start_year = int(date_begin_str)
            end_year = start_year + length - 1
        else:
            raise ValueError(f"series {keycode}: missing both DateBegin and DateEnd")

        multiplier = 1.0
        divisor = 100.0
        unit_str = get_header("Unit")
        if unit_str:
            unit_str = re.sub(r"(?i)mm", "", unit_str).strip()
            if "/" in unit_str:
                parts = unit_str.split("/", 1)
                multiplier = float(parts[0]) if parts[0] else 1.0
                divisor = float(parts[1]) if parts[1] else 1.0
            elif unit_str:
                multiplier = float(unit_str)
                divisor = 1.0

        data_block_type = lines[data_starts[i]].strip()
        data_lines = lines[data_starts[i] + 1 : data_ends[i]]
        clean_data_lines = [l.split(";")[0].rstrip() for l in data_lines if l.split(";")[0].strip()]

        if not clean_data_lines:
            data_vals = []
        elif data_block_type == "DATA:Chrono":
            data_vals = []
            for dl in clean_data_lines:
                tokens = dl.split()
                for k in range(0, len(tokens), 4):
                    try:
                        data_vals.append(float(tokens[k]))
                    except (ValueError, IndexError):
                        pass
        elif len(clean_data_lines[0]) < 60 or ";" in data_lines[0]:
            data_vals = []
            for dl in clean_data_lines:
                for token in dl.split():
                    try:
                        data_vals.append(float(token))
                    except ValueError:
                        pass
        else:
            data_vals_raw = []
            for dl in clean_data_lines:
                for j in range(10):
                    fw = dl[j * 6 : (j + 1) * 6].strip()
                    if fw:
                        try:
                            data_vals_raw.append(float(fw))
                        except ValueError:
                            pass
            if data_vals_raw:
                last_nonzero = max(
                    (k for k, v in enumerate(data_vals_raw) if v != 0),
                    default=-1
                )
                data_vals = data_vals_raw[: last_nonzero + 1]
            else:
                data_vals = []

        data_vals = [v * multiplier / divisor for v in data_vals]
        actual_len = len(data_vals)
        if actual_len < length:
            raise ValueError(f"series {keycode}: too few values (expected {length}, got {actual_len})")
        data_vals = data_vals[:length]

        years = list(range(start_year, start_year + len(data_vals)))
        if start_at_one and start_year < 1:
            shift = 1 - years[0]
            years = [y + shift for y in years]
        elif remove_year_zero and start_year <= 0 <= end_year:
            years = [y + 1 if y >= 0 else y for y in years]
        result.append(Series(
            name=keycode,
            years=np.array(years, dtype=int),
            values=np.array(data_vals, dtype=float),
            filename=os.path.basename(filepath),
        ))

    return result


def read_rwl(filepath: str, name: Optional[str] = None) -> list[Series]:
    series_map: dict[str, tuple[list[int], list[float]]] = {}
    current_name = None

    with open(filepath) as f:
        for line in f:
            line = line.rstrip()
            if not line:
                continue

            series_id = line[:8].strip()
            if not series_id:
                continue

            if series_id != current_name:
                current_name = series_id
                if current_name not in series_map:
                    series_map[current_name] = ([], [])

            year_str = line[8:12].strip()
            data_str = line[12:].strip()

            if not year_str:
                continue

            year = int(year_str)
            vals = []
            for token in data_str.split():
                try:
                    vals.append(float(token))
                except ValueError:
                    continue

            series_map[current_name][0].extend(range(year, year + len(vals)))
            series_map[current_name][1].extend(vals)

    result = []
    for sid, (years, values) in series_map.items():
        result.append(Series(
            name=sid if name is None else name,
            years=np.array(years, dtype=int),
            values=np.array(values, dtype=float),
            filename=os.path.basename(filepath),
        ))
    return result


def read_txt_single(filepath: str) -> Optional[Series]:
    years = []
    values = []
    with open(filepath) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    years.append(int(parts[0]))
                    values.append(float(parts[1]))
                except ValueError:
                    continue

    if not years:
        return None

    basename = os.path.splitext(os.path.basename(filepath))[0]
    return Series(
        name=basename,
        years=np.array(years, dtype=int),
        values=np.array(values, dtype=float),
        filename=os.path.basename(filepath),
    )
