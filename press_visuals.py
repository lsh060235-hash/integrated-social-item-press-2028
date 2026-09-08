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


def _validate_request(request: dict[str, Any], press_commit: str) -> str:
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
        if pair not in _RULES:
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
    else:
        height, ops = _schematic_ops(lines, font)

    image = Image.new("L", (_WIDTH, height), 255)
    draw = ImageDraw.Draw(image)
    for op in ops:
        if op[0] == "text":
            draw.text((op[1], op[2]), op[3], font=font, fill=0)
        elif op[0] == "rect":
            draw.rectangle(op[1:5], outline=0, width=op[5])
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
                f'<line x1="{op[1]:.2f}" y1="{op[2]:.2f}" x2="{op[3]:.2f}" y2="{op[4]:.2f}" stroke="black" stroke-width="{op[5]}"/>'
            )
    width_mm = _WIDTH / _DPI * 25.4
    height_mm = height / _DPI * 25.4
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.2f}mm" height="{height_mm:.2f}mm" '
        f'viewBox="0 0 {_WIDTH} {height}"><rect width="100%" height="100%" fill="white"/>'
        f'<g font-family="Malgun Gothic, Batang" font-size="{_FONT_SIZE}px" fill="black" '
        f'style="white-space:pre">{"".join(svg_ops)}</g>'
        f'<!-- raster font: {html.escape(font_path.name)} --></svg>\n'
    )
    svg_path.write_text(svg, encoding="utf-8")
    return round(width_mm, 2), round(height_mm, 2)


def build_visuals(request: dict[str, Any], out_root: Path, press_commit: str) -> dict[str, Any]:
    """Build figure specs, SVG/PNG pairs, a Forge receipt, and layout metadata."""

    request_sha = _validate_request(request, press_commit)
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
        mode, indices, replace = _RULES[pair]
        source_lines = entry["source_content"].splitlines()
        try:
            core_lines = [source_lines[index] for index in indices]
        except IndexError as exc:
            raise VisualBuildError(f"SOURCE_LINE_MISSING: {pair[0]} {pair[1]}") from exc
        stem = f"{pair[0]}_{pair[1]}"
        spec_rel = Path("specs") / f"{stem}.json"
        svg_rel = Path("svg") / f"{stem}.svg"
        png_rel = Path("png") / f"{stem}.png"
        topology = _topology_for(pair, source_lines, core_lines)
        width_mm, height_mm = _render(
            mode,
            core_lines,
            topology,
            root / png_rel,
            root / svg_rel,
            font,
            font_path,
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
            "font_family": "Malgun Gothic" if font_path.name.lower().startswith("malgun") else "Batang",
            "minimum_font_pt": _FONT_SIZE * 72 / _DPI,
            "color_mode": "black_and_white",
        }
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
