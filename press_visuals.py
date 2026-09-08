"""Deterministic black-and-white figures for the social/PDF press adapter."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


class VisualBuildError(ValueError):
    pass


_DPI = 300
_WIDTH_MM = 112
_WIDTH = int(_WIDTH_MM / 25.4 * _DPI)
_FONT_SIZE = 42  # 10.08 pt at 300 dpi
_LINE_HEIGHT = 58
_MARGIN = 30
_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/batang.ttc"),
)

# Each tuple is render mode, zero-based source line indices, and whether those
# exact lines replace the native body copy. Table-only statistics stay native.
_RULES: dict[tuple[str, str], tuple[str, tuple[int, ...], bool]] = {
    ("FRG-SOC-2028-M01-Q02", "SCENARIO-A"): ("table", (1, 2, 3, 4), False),
    ("FRG-SOC-2028-M01-Q03", "DIARY-A"): ("schematic", (1, 2), True),
    ("FRG-SOC-2028-M01-Q05", "FLOOD-A"): ("table", (1, 2, 3, 4, 6, 7, 8, 9), True),
    ("FRG-SOC-2028-M01-Q07", "FLOW-A"): ("schematic", (1, 2), True),
    ("FRG-SOC-2028-M01-Q08", "CULTURE-A"): ("north_south_map", (1,), True),
    ("FRG-SOC-2028-M01-Q09", "CRAFT-A"): ("vertical_layers", (1,), True),
    ("FRG-SOC-2028-M01-Q11", "LANGUAGE-A"): ("language_grid", (1, 2, 3), True),
    ("FRG-SOC-2028-M01-Q12", "LAND-A"): ("land_grid", (1, 2), True),
    ("FRG-SOC-2028-M01-Q12", "MOVE-B"): ("table", (1, 2, 3, 4), False),
    ("FRG-SOC-2028-M01-Q13", "WORK-A"): ("bar_matrix", (1, 2, 3, 4), True),
    ("FRG-SOC-2028-M01-Q14", "STREET-A"): ("table", (2, 3, 4, 5, 6, 7, 8, 9), False),
    ("FRG-SOC-2028-M01-Q16", "SHIFT-A"): ("schematic", (1, 2, 3, 4, 5, 6), True),
    ("FRG-SOC-2028-M01-Q18", "GAP-A"): ("table", (1, 2, 3, 4, 5), False),
    ("FRG-SOC-2028-M01-Q19", "INDEX-B"): ("bar_list", (2, 3, 4, 5), True),
    ("FRG-SOC-2028-M01-Q20", "ASSET-A"): ("table", (1, 2, 3, 4), False),
    ("FRG-SOC-2028-M01-Q21", "CHAIN-A"): ("table", (0, 1, 2, 3, 4), False),
    ("FRG-SOC-2028-M01-Q22", "MEDIA-A"): ("schematic", (0,), False),
    ("FRG-SOC-2028-M01-Q25", "HOUSE-A"): ("table", (1, 2, 3, 4), False),
}

_REVISION_RULES = dict(_RULES)
_REVISION_RULES[("FRG-SOC-2028-M01-Q03", "DIARY-A")] = ("serif_schematic", (1, 2), True)
_REVISION_RULES[("FRG-SOC-2028-M01-Q14", "STREET-A")] = ("table", (2, 3, 4, 5, 6), False)
for _number, _data, _mode in (
    (5, "FLOOD-A", "revision_flood"),
    (7, "FLOW-A", "revision_flow"),
    (13, "WORK-A", "revision_work_bars"),
    (16, "SHIFT-A", "revision_shift"),
    (19, "INDEX-B", "revision_index_bars"),
):
    _pair = (f"FRG-SOC-2028-M01-Q{_number:02}", _data)
    _, _indices, _replace = _REVISION_RULES[_pair]
    _REVISION_RULES[_pair] = (_mode, _indices, _replace)
for _number, _data, _mode, _indices, _replace in (
    (1, "CASE-B", "table", (1, 2, 3, 4, 5), False),
    (2, "MAP-A", "revision_watershed", (0,), False),
    (2, "DATA-B", "table", (1, 2, 3, 4), False),
    (3, "MAP-A", "revision_culture", (0,), False),
    (5, "DATA-A", "revision_climate", (1, 2, 3, 4, 5, 6), True),
    (6, "DATA-A", "table", (0, 1, 2, 3), False),
    (9, "MAP-A", "revision_transit", (1, 2), False),
    (10, "ARCHIVE-A", "schematic", (0,), True),
    (12, "DATA-A", "table", (1, 2, 3, 4), False),
    (13, "MAP-A", "revision_service", (0, 1), False),
    (16, "DATA-B", "table", (0, 1, 2, 3), False),
    (17, "TIME-A", "schematic", (0,), True),
    (19, "DATA-A", "table", (1, 2, 3, 4, 5), False),
    (20, "MAP-A", "revision_network", (1,), True),
    (21, "DATA-A", "table", (1, 2, 3, 4), False),
    (22, "PLAN-B", "table", (2, 3, 4, 5, 6, 7), False),
    (23, "MAP-B", "revision_coordinates", (1,), False),
    (24, "DATA-A", "table", (1, 2, 3, 4), False),
    (25, "DATA-A", "table", (1, 2, 3, 4), False),
):
    _REVISION_RULES[(f"FRG-SOC-2028-M02-Q{_number:02}", _data)] = (_mode, _indices, _replace)


def build_revision_visuals(request: dict[str, Any], out_root: Path, press_commit: str) -> dict[str, Any]:
    """Render the revised manuscripts, with prose maps inserted beside native text."""
    result = _build_visuals(request, out_root, press_commit, _REVISION_RULES)
    for entry in request["requests"]:
        pair = entry["item_id"], entry["data_id"]
        mode, indices, replace = _REVISION_RULES[pair]
        if mode.startswith("revision_") and not replace:
            result["display"]["|".join(pair)]["insert_before_line"] = entry["source_content"].splitlines()[indices[0]]
    return result


def _revision_topology(mode: str, lines: list[str]) -> dict[str, Any]:
    content = "\n".join(lines)
    if mode == "revision_flood":
        panels = []
        for group in (lines[:4], lines[4:]):
            _, rows = _table_rows(group)
            panels.append({"label": rows[0][0], "rows": rows[1:]})
        return {"type": "paired_spatial_grids", "panels": panels}
    if mode == "revision_flow":
        branches = []
        for line in lines:
            parent, children = line.split(" → ")
            branches.append({"parent": parent, "children": [part.split(": ", 1) for part in children.split(" / ")]})
        return {"type": "fraction_flow", "branches": branches, "fractions": [child[1] for branch in branches for child in branch["children"]]}
    if mode in {"revision_work_bars", "revision_index_bars"}:
        is_work = mode == "revision_work_bars"
        return {"type": "horizontal_bar_chart", "series": _parse_series("bar_matrix" if is_work else "bar_list", lines), "categories": _cells(lines[0])[1:] if is_work else [], "unit": "kWh/주" if is_work else "지수", "segment_value": 10}
    if mode == "revision_shift":
        intervals = [re.findall(r"\d{2}:\d{2}", line)[:2] for line in lines]
        if any(len(interval) != 2 for interval in intervals):
            raise VisualBuildError("TIMELINE_INTERVAL_UNREADABLE")
        return {"type": "time_intervals", "intervals": intervals, "descriptions": lines}
    if mode == "revision_watershed":
        match = re.fullmatch(r"가상 유역에서 서쪽 지류는 (.+?)을 지나 (\w)로, 동쪽 지류는 (.+?)를 지나 (\w)로 흐른다. (\w)와 (\w)를 지난 물은 (\w)에서 합류한다.", content)
        if match is None or match.group(2, 4) != match.group(5, 6):
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: watershed")
        west, p, east, q, _, _, r = match.groups()
        return {"type": "watershed", "edges": [[west, p], [east, q], [p, r], [q, r]], "west": west, "east": east, "nodes": [p, q, r]}
    if mode == "revision_climate":
        _, rows = _table_rows(lines)
        return {"type": "seasonal_climate", "periods": rows[0][1:], "series": [{"label": row[0], "values": [int(v) for v in row[1:]]} for row in rows[1:]]}
    if mode == "revision_network":
        edges = [[a, b, int(value)] for a, b, value in re.findall(r"([A-Z])—([A-Z]): (\d+)건", content)]
        if len(edges) != 4:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: network")
        return {"type": "international_city_network", "edges": edges}
    if mode == "revision_coordinates":
        points = [[name, int(x), int(y)] for name, x, y in re.findall(r"([A-Z])=\((\d+),(\d+)\)", content)]
        if len(points) != 3:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: coordinates")
        return {"type": "coordinate_grid", "points": points}
    if mode == "revision_transit":
        before = re.search(r"([A-Z])—([A-Z]) 직행버스 (\d+)분", lines[0])
        after = re.findall(r"([A-Z])—([A-Z]) (버스|철도) (\d+)분", lines[1])
        wait = re.search(r"([A-Z])의 환승 대기는 (\d+)분", lines[1])
        if before is None or len(after) != 2 or wait is None:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: transit")
        return {"type": "transit_network", "before": list(before.groups()), "after": [list(edge) for edge in after], "wait": list(wait.groups())}
    if mode == "revision_service":
        edges = [[a, b, int(t)] for a, b, t in re.findall(r"([WE])↔(서관|동관) (\d+)분", content)]
        if len(edges) != 4:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: service")
        return {"type": "service_access", "edges": edges}
    if mode == "revision_culture":
        # Prose remains native; the figure repeats only explicitly stated relations.
        if not all(value in content for value in ("P는 해안의 국제 항구", "Q는 내륙의 계절적 범람 하천", "P와 바다 건너 R", "오랜 이주 경로", "Q와 R 사이에는 그 경로가 없다")):
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: culture")
        return {"type": "culture_location", "connections": [["P", "국제 항구"], ["P", "R", "오랜 이주 경로"]], "unconnected": [["Q", "R"]]}
    raise VisualBuildError(f"UNSUPPORTED_RENDER_MODE: {mode}")


def _arrow_ops(x1, y1, x2, y2):
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    return [("line", x1, y1, x2, y2, 3)] + [
        ("line", x2, y2, x2 - 22 * math.cos(angle + delta), y2 - 22 * math.sin(angle + delta), 3)
        for delta in (-0.45, 0.45)
    ]


def _revision_ops(mode, topology, font):
    ops = []

    def text(x, y, value, attrs=None):
        ops.append(("text", x, y, value, attrs or {}))

    def node(x, y, value):
        width = max(100, font.getlength(value) + 34)
        ops.append(("rect", x - width / 2, y, x + width / 2, y + 70, 3))
        text(x - font.getlength(value) / 2, y + 10, value, {"data-node": value})

    if mode == "revision_flood":
        for index, panel in enumerate(topology["panels"]):
            left = 30 + index * 660
            text(left + 20, 25, panel["label"])
            for row, cells in enumerate(panel["rows"]):
                for column, value in enumerate(cells):
                    x, y = left + column * 200, 100 + row * 125
                    ops.append(("rect", x, y, x + 200, y + 125, 2, {"data-flood-cell": value.split(":")[0], "data-panel": str(index)}))
                    text(x + (200 - font.getlength(value)) / 2, y + 40, value)
        return 380, ops
    if mode == "revision_flow":
        first, second = topology["branches"]

        def flow_box(x, y, value, width):
            parts = _wrap(value, font, width - 36)
            box_height = len(parts) * 58 + 20
            ops.append(("rect", x - width / 2, y, x + width / 2, y + box_height, 2))
            for i, part in enumerate(parts):
                text(x - font.getlength(part) / 2, y + 10 + i * 58, part)
            return box_height

        root = first["parent"]
        flow_box(660, 20, root, 300)
        for i, (label, fraction) in enumerate(first["children"]):
            x = (360, 1080)[i]
            edge = _arrow_ops(660, 98, x, 235)
            edge[0] += ({"data-flow-edge": f"0-{i}"},)
            ops.extend(edge)
            text((120, 960)[i], 145, fraction)
            flow_box(x, 235, label, 270)
        for i, (label, fraction) in enumerate(second["children"]):
            x = (250, 790)[i]
            edge = _arrow_ops(360, 313, x, 500)
            edge[0] += ({"data-flow-edge": f"1-{i}"},)
            ops.extend(edge)
            text((35, 690)[i], 385, fraction)
            flow_box(x, 500, label, (420, 510)[i])
        return 665, ops
    if mode in {"revision_work_bars", "revision_index_bars"}:
        is_work = mode == "revision_work_bars"
        rows = []
        for series in topology["series"]:
            for i, value in enumerate(series["values"]):
                rows.append((series["label"], topology["categories"][i] if is_work else series["label"], value))
        axis_x, axis_width = 440, 770
        row_height = 70
        top = 155
        height = top + len(rows) * row_height + (60 if is_work else 0) + 35
        text(30, 15, f'({topology["unit"]})')
        if is_work:
            text(30, 80, "대안")
        ops.append(("line", axis_x, 108, axis_x + axis_width, 108, 2))
        ops.append(("line", axis_x, 108, axis_x, height - 35, 2, {"data-zero-axis": "0"}))
        for tick in range(0, 121, 20):
            x = axis_x + axis_width * tick / 120
            ops.append(("line", x, 100, x, 116, 2))
            text(x - font.getlength(str(tick)) / 2, 48, str(tick), {"data-axis-tick": str(tick)})
        y = top
        for index, (group, label, value) in enumerate(rows):
            if is_work and index % 3 == 0:
                if index:
                    y += 30
                text(35, y + row_height, group)
            text(110 if is_work else 35, y + 2, label, {"data-bar-label": str(index)})
            ops.extend(_bar_segment_ops(axis_x + 2, y + 7, axis_width, 40, value, 120, group))
            text(axis_x + axis_width * value / 120 + 10, y, str(value))
            y += row_height
        return height, ops
    if mode == "revision_shift":
        def minute(value):
            hour, minutes = map(int, value.split(":"))
            return hour * 60 + minutes

        intervals = topology["intervals"]
        first = minute(intervals[0][0])
        span = minute(intervals[-1][1]) - first
        left, width = 65, 1160
        for index, (start, end) in enumerate(intervals):
            x1 = left + (minute(start) - first) * width / span
            x2 = left + (minute(end) - first) * width / span
            ops.append(("rect", x1, 90, x2, 155, 2, {"data-time-interval": f"{start}-{end}"}))
        boundaries = [interval[0] for interval in intervals] + [intervals[-1][1]]
        for index, time in enumerate(boundaries):
            x = left + (minute(time) - first) * width / span
            above = index in (0, 1, 3, 5)
            ops.append(("line", x, 75 if above else 155, x, 90 if above else 170, 2))
            text(x - font.getlength(time) / 2, 20 if above else 175, time)
        body_height, body = _schematic_ops(topology["descriptions"], font)
        for op in body:
            shifted = list(op)
            shifted[2] += 245
            if op[0] != "text":
                shifted[4] += 245
            ops.append(tuple(shifted))
        return body_height + 245, ops

    if mode == "revision_watershed":
        p, q, r = topology["nodes"]
        for x, label, station in [(320, topology["west"], p), (1000, topology["east"], q)]:
            text(x - 85, 25, "서쪽 지류" if x == 320 else "동쪽 지류")
            node(x, 105, label)
            ops.extend(_arrow_ops(x, 175, x, 245))
            node(x, 245, station)
            ops.extend(_arrow_ops(x, 315, 660, 435))
        node(660, 435, r)
        return 540, ops
    if mode == "revision_culture":
        ops.extend([("rect", 40, 40, 790, 495, 2), ("line", 790, 40, 790, 495, 3)])
        text(60, 50, "같은 국가")
        text(840, 55, "바다")
        node(280, 130, "Q")
        text(75, 220, "내륙 · 계절적 범람 하천")
        ops.append(("line", 650, 395, 1140, 395, 3))
        node(650, 360, "P")
        text(420, 440, "해안 · 국제 항구")
        node(1140, 360, "R")
        text(820, 290, "오랜 이주 경로")
        return 530, ops
    if mode == "revision_network":
        positions = {"A": (410, 105), "B": (850, 105), "C": (850, 410), "D": (190, 410)}
        labels = {("A", "B"): (575, 45), ("A", "C"): (625, 225), ("A", "D"): (170, 235), ("B", "C"): (890, 255)}
        for a, b, value in topology["edges"]:
            x1, y1 = positions[a]
            x2, y2 = positions[b]
            ops.append(("line", x1, y1 + 35, x2, y2 + 35, 3, {"data-edge": a + "-" + b, "data-value": str(value)}))
            text(*labels[(a, b)], f"{value}건")
        for name, (x, y) in positions.items():
            node(x, y, name)
        text(375, 515, "그 밖의 협력은 없다.")
        return 590, ops
    if mode == "revision_coordinates":
        origin_x, origin_y, step = 350, 610, 220
        for index in range(3):
            ops.append(("line", origin_x, origin_y - index * step, origin_x + 2 * step, origin_y - index * step, 2))
            ops.append(("line", origin_x + index * step, origin_y, origin_x + index * step, origin_y - 2 * step, 2))
            text(origin_x + index * step - 12, origin_y + 25, str(index))
            text(origin_x - 65, origin_y - index * step - 20, str(index))
        text(495, 50, "북쪽 ↑")
        text(860, 605, "→ 동쪽")
        for name, x, y in topology["points"]:
            px, py = origin_x + x * step, origin_y - y * step
            ops.append(("fill", px - 7, py - 7, px + 7, py + 7))
            text(px + 20, py - 62, f"{name}=({x},{y})", {"data-node": name})
        return 700, ops
    if mode == "revision_transit":
        a, c, minutes = topology["before"]
        text(45, 25, "개편 전")
        ops.append(("line", 190, 145, 1110, 145, 3))
        text(485, 75, f"직행버스 {minutes}분")
        node(190, 110, a)
        node(1110, 110, c)
        text(45, 245, "개편 후")
        for index, (start, end, transport, duration) in enumerate(topology["after"]):
            x = 190 + index * 460
            ops.append(("line", x, 390, x + 460, 390, 3))
            text(x + 90, 310, f"{transport} {duration}분")
            node(x, 355, start)
            node(x + 460, 355, end)
        text(440, 465, f'{topology["wait"][0]} 환승 대기 {topology["wait"][1]}분')
        return 550, ops
    if mode == "revision_service":
        text(160, 20, "서쪽 W구역")
        text(890, 20, "동쪽 E구역")
        positions = {"W": (250, 100), "E": (1070, 100), "서관": (250, 450), "동관": (1070, 450)}
        labels = {("W", "서관"): (100, 270), ("W", "동관"): (475, 185), ("E", "서관"): (780, 145), ("E", "동관"): (1110, 270)}
        for start, end, duration in topology["edges"]:
            x1, y1 = positions[start]
            x2, y2 = positions[end]
            ops.append(("line", x1, y1 + 35, x2, y2 + 35, 3, {"data-edge": start + "-" + end}))
            text(*labels[(start, end)], f"{duration}분")
        for name, (x, y) in positions.items():
            node(x, y, name)
        return 575, ops
    if mode == "revision_climate":
        panel_width = (_WIDTH - 60) / 2
        for index, series in enumerate(topology["series"]):
            x = 30 + (index % 2) * panel_width
            y = 30 + (index // 2) * 480
            text(x + 40, y, series["label"] + (" (℃)" if index % 2 == 0 else " (mm)"))
            baseline = y + 340
            ops.append(("line", x + 35, baseline, x + panel_width - 15, baseline, 2))
            scale = 30 if index % 2 == 0 else 300
            previous_label_end = x
            for position, (period, value) in enumerate(zip(topology["periods"], series["values"])):
                center = x + 92 + position * 140
                top = baseline - value / scale * 225
                ops.append(("rect", center - 34, top, center + 34, baseline, 3, {"data-climate-value": str(value), "data-series": series["label"], "data-period": period}))
                text(center - font.getlength(str(value)) / 2, top - 55, str(value))
                label_x = max(center - font.getlength(period) / 2, previous_label_end + 20)
                text(label_x, baseline + 12, period)
                previous_label_end = label_x + font.getlength(period)
        return 990, ops
    raise VisualBuildError(f"UNSUPPORTED_RENDER_MODE: {mode}")


def _canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise VisualBuildError("INVALID_VISUAL_REQUEST") from exc
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _font() -> tuple[ImageFont.FreeTypeFont, Path]:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), _FONT_SIZE), path
    raise VisualBuildError("KOREAN_FONT_UNAVAILABLE")


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    if not text:
        return [""]
    output: list[str] = []
    rest = text
    while rest:
        if font.getlength(rest) <= width:
            output.append(rest)
            break
        end = 1
        while end < len(rest) and font.getlength(rest[: end + 1]) <= width:
            end += 1
        split = rest.rfind(" ", 0, end)
        if split <= 0:
            split = end
        output.append(rest[:split].rstrip())
        rest = rest[split:].lstrip()
    return output


def _cells(line: str) -> list[str]:
    parts = [part.strip() for part in line.split("|")]
    if parts and not parts[0]:
        parts.pop(0)
    if parts and not parts[-1]:
        parts.pop()
    return parts


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _table_rows(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    prose: list[str] = []
    rows: list[list[str]] = []
    for line in lines:
        if "|" not in line:
            prose.append(line)
            continue
        cells = _cells(line)
        if not _is_separator(cells):
            rows.append(cells)
    return prose, rows


def _parse_series(mode: str, lines: list[str]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    if mode == "bar_matrix":
        for line in lines[1:]:
            cells = _cells(line)
            values = []
            for cell in cells[1:]:
                match = re.search(r"(\d[\d,]*)\s*$", cell)
                if match is None:
                    raise VisualBuildError("BAR_VALUE_UNREADABLE")
                values.append(int(match.group(1).replace(",", "")))
            series.append({"label": cells[0], "values": values})
    elif mode == "bar_list":
        for line in lines:
            match = re.fullmatch(r"(.+?)\s+█+\s+(\d[\d,]*)\s*", line)
            if match is None:
                raise VisualBuildError("BAR_VALUE_UNREADABLE")
            series.append(
                {"label": match.group(1).strip(), "values": [int(match.group(2).replace(",", ""))]}
            )
    return series


def _topology_for(
    pair: tuple[str, str], source_lines: list[str], core_lines: list[str]
) -> dict[str, Any] | None:
    if pair[1] == "CULTURE-A":
        match = re.fullmatch(
            r"(북쪽): (.+?\[([^]]+)\]) ━ (남쪽): (.+?\[([^]]+)\])", core_lines[0]
        )
        legend = re.search(r"━=([^.]*)", source_lines[2])
        if match is None or legend is None:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: CULTURE-A")
        return {
            "type": "north_south_map",
            "nodes": [
                {"position": match.group(1), "text": match.group(2), "tokens": match.group(3).split("·")},
                {"position": match.group(4), "text": match.group(5), "tokens": match.group(6).split("·")},
            ],
            "connector": {"symbol": "━", "meaning": legend.group(1)},
        }
    if pair[1] == "CRAFT-A":
        direction, layer_text = core_lines[0].split(": ", 1)
        return {
            "type": "vertical_layers",
            "direction_label": direction,
            "layers": layer_text.split(" → "),
        }
    if pair[1] == "LANGUAGE-A":
        direction = re.fullmatch(r"(서쪽) ← (\[[^]]+\]) (\[[^]]+\]) (\[[^]]+\]) → (동쪽)", core_lines[0])
        if direction is None:
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: LANGUAGE-A")
        layers = []
        for line in core_lines[1:]:
            label, values = line.split(": ", 1)
            layers.append({"label": label, "values": [value.strip() for value in values.split(" / ")]})
        return {
            "type": "west_east_language_grid",
            "direction": {"west": direction.group(1), "east": direction.group(5)},
            "districts": list(direction.groups()[1:4]),
            "layers": layers,
        }
    if pair[1] == "LAND-A":
        rows = []
        for line in core_lines:
            label, cells = line.split(":", 1)
            rows.append({"label": label.strip(), "cells": re.findall(r"\[[^]]+\]", cells)})
        if any(len(row["cells"]) != 2 for row in rows):
            raise VisualBuildError("MAP_TOPOLOGY_UNREADABLE: LAND-A")
        return {"type": "land_use_grid", "rows": rows}
    return None


def _validate_request(request: dict[str, Any], press_commit: str, rules=None) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", press_commit):
        raise VisualBuildError("PRESS_COMMIT must be a real 40-character git object id")
    if request.get("schema_version") != "integrated-social-visual-handoff-v1":
        raise VisualBuildError("VISUAL_REQUEST_SCHEMA")
    entries = request.get("requests")
    if not isinstance(entries, list) or not entries:
        raise VisualBuildError("VISUAL_REQUESTS")
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        pair = entry.get("item_id"), entry.get("data_id")
        if pair in seen:
            raise VisualBuildError("DUPLICATE_VISUAL_REQUEST")
        seen.add(pair)
        if pair not in (rules if rules is not None else _RULES):
            raise VisualBuildError(f"UNSUPPORTED_VISUAL_REQUEST: {pair[0]} {pair[1]}")
        content = entry.get("source_content")
        if not isinstance(content, str) or hashlib.sha256(content.encode("utf-8")).hexdigest() != entry.get(
            "source_content_sha256"
        ):
            raise VisualBuildError(f"SOURCE_CONTENT_SHA256: {pair[0]} {pair[1]}")
    return _canonical_sha256(request)


def _schematic_ops(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, list[tuple]]:
    wrapped = [_wrap(line, font, _WIDTH - 2 * (_MARGIN + 18)) for line in lines]
    heights = [len(parts) * _LINE_HEIGHT + 24 for parts in wrapped]
    height = 2 * _MARGIN + sum(heights)
    ops: list[tuple] = [("rect", _MARGIN, _MARGIN, _WIDTH - _MARGIN, height - _MARGIN, 3)]
    y = _MARGIN
    for index, parts in enumerate(wrapped):
        if index:
            ops.append(("line", _MARGIN, y, _WIDTH - _MARGIN, y, 2))
        for part in parts:
            ops.append(("text", _MARGIN + 18, y + 12, part))
            y += _LINE_HEIGHT
        y += 24
    return height, ops


def _table_ops(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, list[tuple]]:
    prose, rows = _table_rows(lines)
    ops: list[tuple] = []
    y = _MARGIN
    for line in prose:
        wrapped = _wrap(line, font, _WIDTH - 2 * _MARGIN)
        for part in wrapped:
            ops.append(("text", _MARGIN, y, part))
            y += _LINE_HEIGHT
        y += 12
    if not rows:
        return _schematic_ops(lines, font)
    columns = max(len(row) for row in rows)
    cell_width = (_WIDTH - 2 * _MARGIN) / columns
    for row in rows:
        row += [""] * (columns - len(row))
        wrapped_cells = [_wrap(cell, font, int(cell_width) - 20) for cell in row]
        row_height = max(len(parts) for parts in wrapped_cells) * _LINE_HEIGHT + 20
        for col, parts in enumerate(wrapped_cells):
            x1 = _MARGIN + col * cell_width
            x2 = _MARGIN + (col + 1) * cell_width
            ops.append(("rect", x1, y, x2, y + row_height, 2))
            for line_number, part in enumerate(parts):
                ops.append(("text", x1 + 10, y + 10 + line_number * _LINE_HEIGHT, part))
        y += row_height
    return int(y + _MARGIN), ops


def _bar_matrix_ops(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, list[tuple]]:
    headers = _cells(lines[0])
    series = _parse_series("bar_matrix", lines)
    max_value = max(value for entry in series for value in entry["values"])
    first_width = 120
    other_width = (_WIDTH - 2 * _MARGIN - first_width) / (len(headers) - 1)
    widths = [first_width] + [other_width] * (len(headers) - 1)
    wrapped_headers = [_wrap(label, font, int(width) - 18) for label, width in zip(headers, widths)]
    header_height = max(len(parts) for parts in wrapped_headers) * _LINE_HEIGHT + 18
    row_height = 82
    height = int(2 * _MARGIN + header_height + len(series) * row_height)
    ops: list[tuple] = []
    y = _MARGIN
    x = _MARGIN
    for width, parts in zip(widths, wrapped_headers):
        ops.append(("rect", x, y, x + width, y + header_height, 2))
        for number, part in enumerate(parts):
            ops.append(("text", x + 9, y + 9 + number * _LINE_HEIGHT, part))
        x += width
    y += header_height
    for entry in series:
        x = _MARGIN
        ops.append(("rect", x, y, x + widths[0], y + row_height, 2))
        ops.append(("text", x + 12, y + 15, entry["label"]))
        x += widths[0]
        for width, value in zip(widths[1:], entry["values"]):
            ops.append(("rect", x, y, x + width, y + row_height, 2))
            chart_width = width - 86
            ops.extend(
                _bar_segment_ops(
                    x + 10,
                    y + 20,
                    chart_width,
                    40,
                    value,
                    max_value,
                    entry["label"],
                )
            )
            ops.append(("text", x + width - 72, y + 14, str(value)))
            x += width
        y += row_height
    return height, ops


def _bar_list_ops(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, list[tuple]]:
    series = _parse_series("bar_list", lines)
    max_value = max(entry["values"][0] for entry in series)
    label_width = 290
    row_height = 82
    height = 2 * _MARGIN + len(series) * row_height
    ops: list[tuple] = [("rect", _MARGIN, _MARGIN, _WIDTH - _MARGIN, height - _MARGIN, 3)]
    y = _MARGIN
    for number, entry in enumerate(series):
        if number:
            ops.append(("line", _MARGIN, y, _WIDTH - _MARGIN, y, 2))
        value = entry["values"][0]
        ops.append(("text", _MARGIN + 12, y + 15, entry["label"]))
        chart_x = _MARGIN + label_width
        chart_width = _WIDTH - _MARGIN - chart_x - 100
        ops.extend(
            _bar_segment_ops(chart_x, y + 20, chart_width, 40, value, max_value, entry["label"])
        )
        ops.append(("text", _WIDTH - _MARGIN - 85, y + 14, str(value)))
        y += row_height
    return height, ops


def _bar_segment_ops(
    x: float,
    y: float,
    maximum_width: float,
    height: float,
    value: int,
    maximum_value: int,
    series: str,
) -> list[tuple]:
    if value % 10:
        raise VisualBuildError("BAR_VALUE_NOT_TEN_UNIT")
    cell_width = maximum_width * 10 / maximum_value
    gap = 3
    return [
        (
            "fill",
            x + index * cell_width,
            y,
            x + (index + 1) * cell_width - gap,
            y + height,
            {"data-series": series, "data-value": str(value), "data-segment": str(index + 1)},
        )
        for index in range(value // 10)
    ]


def _north_south_ops(topology: dict[str, Any]) -> tuple[int, list[tuple]]:
    height = 430
    box_x1, box_x2 = 210, _WIDTH - 210
    center = _WIDTH / 2
    north, south = topology["nodes"]
    connector = topology["connector"]
    ops = [
        ("rect", box_x1, 30, box_x2, 115, 3),
        ("text", box_x1 + 22, 45, f'{north["position"]}: {north["text"]}', {"data-node": "north"}),
        ("line", center, 115, center, 165, 3),
        ("rect", 245, 165, _WIDTH - 245, 245, 2),
        ("text", 270, 181, f'{connector["symbol"]}={connector["meaning"]}'),
        ("line", center, 245, center, 295, 3),
        ("rect", box_x1, 295, box_x2, 380, 3),
        ("text", box_x1 + 22, 310, f'{south["position"]}: {south["text"]}', {"data-node": "south"}),
    ]
    return height, ops


def _vertical_layer_ops(topology: dict[str, Any]) -> tuple[int, list[tuple]]:
    layers = topology["layers"]
    box_height = 68
    height = 2 * _MARGIN + _LINE_HEIGHT + len(layers) * box_height
    ops: list[tuple] = [("text", _MARGIN, _MARGIN, topology["direction_label"])]
    y = _MARGIN + _LINE_HEIGHT
    for index, layer in enumerate(layers):
        ops.append(("rect", 210, y, _WIDTH - 210, y + box_height, 2))
        ops.append(("text", 235, y + 10, layer, {"data-layer": str(index)}))
        y += box_height
    return height, ops


def _language_grid_ops(topology: dict[str, Any], font: ImageFont.FreeTypeFont) -> tuple[int, list[tuple]]:
    label_width = 280
    content_width = _WIDTH - 2 * _MARGIN - label_width
    cell_width = content_width / 3
    direction_height = 64
    header_height = 74
    row_height = 132
    height = int(2 * _MARGIN + direction_height + header_height + 2 * row_height)
    ops: list[tuple] = [
        ("text", _MARGIN, _MARGIN, f'{topology["direction"]["west"]} ←'),
        ("text", _WIDTH - _MARGIN - 150, _MARGIN, f'→ {topology["direction"]["east"]}'),
    ]
    y = _MARGIN + direction_height
    x = _MARGIN + label_width
    for index, district in enumerate(topology["districts"]):
        ops.append(("rect", x, y, x + cell_width, y + header_height, 2))
        ops.append(
            ("text", x + 12, y + 10, district, {"data-district": ("다", "바", "사")[index]})
        )
        x += cell_width
    y += header_height
    for row_index, layer in enumerate(topology["layers"]):
        ops.append(("rect", _MARGIN, y, _MARGIN + label_width, y + row_height, 2))
        for number, part in enumerate(_wrap(layer["label"], font, label_width - 20)):
            ops.append(("text", _MARGIN + 10, y + 10 + number * _LINE_HEIGHT, part))
        x = _MARGIN + label_width
        for column, value in enumerate(layer["values"]):
            ops.append(("rect", x, y, x + cell_width, y + row_height, 2))
            for number, part in enumerate(_wrap(value, font, int(cell_width) - 20)):
                ops.append(
                    (
                        "text",
                        x + 10,
                        y + 10 + number * _LINE_HEIGHT,
                        part,
                        {"data-language-layer": f"{row_index}-{column}"},
                    )
                )
            x += cell_width
        y += row_height
    return height, ops


def _land_grid_ops(topology: dict[str, Any]) -> tuple[int, list[tuple]]:
    label_width = 260
    cell_width = (_WIDTH - 2 * _MARGIN - label_width) / 2
    row_height = 104
    height = int(2 * _MARGIN + len(topology["rows"]) * row_height)
    ops: list[tuple] = []
    y = _MARGIN
    for row in topology["rows"]:
        ops.append(("rect", _MARGIN, y, _MARGIN + label_width, y + row_height, 2))
        ops.append(("text", _MARGIN + 12, y + 22, row["label"]))
        x = _MARGIN + label_width
        for cell in row["cells"]:
            name = cell[1]
            ops.append(("rect", x, y, x + cell_width, y + row_height, 2, {"data-land-cell": name}))
            ops.append(("text", x + 12, y + 22, cell))
            x += cell_width
        y += row_height
    return height, ops


def _render(
    mode: str,
    lines: list[str],
    topology: dict[str, Any] | None,
    png_path: Path,
    svg_path: Path,
    font: ImageFont.FreeTypeFont,
    font_path: Path,
) -> tuple[float, float]:
    if mode == "table":
        height, ops = _table_ops(lines, font)
    elif mode == "bar_matrix":
        height, ops = _bar_matrix_ops(lines, font)
    elif mode == "bar_list":
        height, ops = _bar_list_ops(lines, font)
    elif mode == "north_south_map":
        height, ops = _north_south_ops(topology or {})
    elif mode == "vertical_layers":
        height, ops = _vertical_layer_ops(topology or {})
    elif mode == "language_grid":
        height, ops = _language_grid_ops(topology or {}, font)
    elif mode == "land_grid":
        height, ops = _land_grid_ops(topology or {})
    elif mode.startswith("revision_"):
        height, ops = _revision_ops(mode, topology or {}, font)
    else:
        height, ops = _schematic_ops(lines, font)

    image = Image.new("L", (_WIDTH, height), 255)
    draw = ImageDraw.Draw(image)
    for op in ops:
        if op[0] == "text":
            draw.text((op[1], op[2]), op[3], font=font, fill=0)
        elif op[0] == "rect":
            draw.rectangle(op[1:5], fill=255, outline=0, width=op[5])
        elif op[0] == "fill":
            draw.rectangle(op[1:5], fill=0)
        else:
            draw.line(op[1:5], fill=0, width=op[5])
    image.save(png_path, format="PNG", dpi=(_DPI, _DPI), optimize=True)

    def attributes(op: tuple, index: int) -> str:
        if len(op) > index and isinstance(op[index], dict):
            return "".join(
                f' {html.escape(str(key))}="{html.escape(str(value), quote=True)}"'
                for key, value in op[index].items()
            )
        return ""

    svg_ops: list[str] = []
    for op in ops:
        if op[0] == "text":
            svg_ops.append(
                f'<text x="{op[1]:.2f}" y="{op[2]:.2f}" dominant-baseline="hanging"{attributes(op, 4)}>{html.escape(op[3])}</text>'
            )
        elif op[0] == "rect":
            svg_ops.append(
                f'<rect x="{op[1]:.2f}" y="{op[2]:.2f}" width="{op[3]-op[1]:.2f}" height="{op[4]-op[2]:.2f}" fill="white" stroke="black" stroke-width="{op[5]}"{attributes(op, 6)}/>'
            )
        elif op[0] == "fill":
            svg_ops.append(
                f'<rect x="{op[1]:.2f}" y="{op[2]:.2f}" width="{op[3]-op[1]:.2f}" height="{op[4]-op[2]:.2f}" fill="black"{attributes(op, 5)}/>'
            )
        else:
            svg_ops.append(
                f'<line x1="{op[1]:.2f}" y1="{op[2]:.2f}" x2="{op[3]:.2f}" y2="{op[4]:.2f}" stroke="black" stroke-width="{op[5]}"{attributes(op, 6)}/>'
            )
    width_mm = _WIDTH / _DPI * 25.4
    height_mm = height / _DPI * 25.4
    svg_font_family = "Batang" if font_path.name.lower().startswith("batang") else "Malgun Gothic"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.2f}mm" height="{height_mm:.2f}mm" '
        f'viewBox="0 0 {_WIDTH} {height}"><rect width="100%" height="100%" fill="white"/>'
        f'<g font-family="{svg_font_family}" font-size="{_FONT_SIZE}px" fill="black" '
        f'style="white-space:pre">{"".join(svg_ops)}</g>'
        f'<!-- raster font: {html.escape(font_path.name)} --></svg>\n'
    )
    svg_path.write_text(svg, encoding="utf-8")
    return round(width_mm, 2), round(height_mm, 2)


def build_visuals(request: dict[str, Any], out_root: Path, press_commit: str) -> dict[str, Any]:
    """Build figure specs, SVG/PNG pairs, a Forge receipt, and layout metadata."""
    return _build_visuals(request, out_root, press_commit, _RULES)


def _build_visuals(request, out_root, press_commit, rules):

    request_sha = _validate_request(request, press_commit, rules)
    root = Path(out_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise VisualBuildError("OUTPUT_ROOT")
    directories = {name: root / name for name in ("specs", "svg", "png")}
    for directory in directories.values():
        directory.mkdir(exist_ok=True)
        if not directory.resolve().is_relative_to(root):
            raise VisualBuildError("UNSAFE_OUTPUT_ROOT")

    font, font_path = _font()
    bindings: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    display: dict[str, dict[str, Any]] = {}
    for entry in request["requests"]:
        pair = entry["item_id"], entry["data_id"]
        mode, indices, replace = rules[pair]
        source_lines = entry["source_content"].splitlines()
        try:
            core_lines = [source_lines[index] for index in indices]
        except IndexError as exc:
            raise VisualBuildError(f"SOURCE_LINE_MISSING: {pair[0]} {pair[1]}") from exc
        stem = f"{pair[0]}_{pair[1]}"
        spec_rel = Path("specs") / f"{stem}.json"
        svg_rel = Path("svg") / f"{stem}.svg"
        png_rel = Path("png") / f"{stem}.png"
        topology = (_revision_topology(mode, core_lines) if mode.startswith("revision_")
                    else _topology_for(pair, source_lines, core_lines))
        figure_font, figure_font_path = font, font_path
        if mode == "serif_schematic":
            figure_font_path = Path("C:/Windows/Fonts/batang.ttc")
            figure_font = ImageFont.truetype(str(figure_font_path), _FONT_SIZE)
        width_mm, height_mm = _render(
            mode,
            core_lines,
            topology,
            root / png_rel,
            root / svg_rel,
            figure_font,
            figure_font_path,
        )
        core_variables: dict[str, Any] = {"lines": core_lines}
        if topology is not None:
            core_variables["topology"] = topology
        if mode == "table":
            prose, rows = _table_rows(core_lines)
            core_variables.update({"prose_lines": prose, "table_rows": rows})
        elif mode in {"bar_matrix", "bar_list"}:
            core_variables["series"] = _parse_series(mode, core_lines)
        spec = {
            "schema_version": "integrated-social-press-figure-spec-v1",
            "figure_spec_id": f"FIG-{pair[0]}-{pair[1]}",
            "item_id": pair[0],
            "data_id": pair[1],
            "material_kind": entry["material_kind"],
            "data_grammar": entry["data_grammar"],
            "preserve": entry["preserve"],
            "request_sha256": request_sha,
            "source_content": entry["source_content"],
            "source_content_sha256": entry["source_content_sha256"],
            "render_mode": mode,
            "core_variables": core_variables,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "font_family": "Malgun Gothic" if figure_font_path.name.lower().startswith("malgun") else "Batang",
            "minimum_font_pt": _FONT_SIZE * 72 / _DPI,
            "color_mode": "black_and_white",
        }
        if mode.startswith("revision_") and not replace:
            spec["insert_before_line"] = core_lines[0]
        spec_path = root / spec_rel
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        binding = {
            "item_id": pair[0],
            "data_id": pair[1],
            "figure_spec_id": spec["figure_spec_id"],
            "figure_spec_sha256": _file_sha256(spec_path),
            "rendered_asset_sha256": _file_sha256(root / png_rel),
        }
        bindings.append(binding)
        artifacts.append(
            {
                "item_id": pair[0],
                "data_id": pair[1],
                "figure_spec_path": spec_rel.as_posix(),
                "rendered_asset_path": png_rel.as_posix(),
            }
        )
        display["|".join(pair)] = {
            "png_path": png_rel.as_posix(),
            "svg_path": svg_rel.as_posix(),
            "width_mm": width_mm,
            "height_mm": height_mm,
            "replace_lines": core_lines if replace else [],
        }

    receipt = {
        "schema_version": "integrated-social-visual-receipt-v1",
        "campaign_id": request["campaign_id"],
        "status": "COMPLETE",
        "request_sha256": request_sha,
        "press_contract_version": "integrated-social-press-0.1",
        "press_commit": press_commit,
        "bindings": bindings,
    }
    return {"receipt": receipt, "artifacts": artifacts, "display": display}
