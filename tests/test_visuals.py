import copy
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image


sys.dont_write_bytecode = True
ROOT = Path(__file__).parents[1]
FORGE = ROOT.parent / "integrated-social-item-forge"
sys.path.insert(0, str(FORGE / "src"))

from integrated_social_forge.visual_handoff import (  # noqa: E402
    VisualHandoffError,
    validate_visual_artifacts,
)


HANDOFF = FORGE / "campaigns" / "FRG-SOC-2028-M01" / "press" / "visual_handoff.json"


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from press_visuals import build_visuals

    request = json.loads(HANDOFF.read_text(encoding="utf-8"))
    press_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    out_root = tmp_path_factory.mktemp("visuals")
    result = build_visuals(request, out_root, press_commit)
    return request, out_root, result


def test_builds_exact_visual_specs_and_validated_png_assets(built):
    request, out_root, result = built

    assert set(result) == {"receipt", "artifacts", "display"}
    assert len(result["receipt"]["bindings"]) == 18
    assert len(result["artifacts"]) == 18
    assert len(result["display"]) == 18
    assert result["receipt"]["request_sha256"] == canonical_sha256(request)
    report = validate_visual_artifacts(
        request, result["receipt"], result["artifacts"], out_root
    )
    assert report["byte_status"] == "VERIFIED"
    assert report["verified_binding_count"] == 18

    requests = {(entry["item_id"], entry["data_id"]): entry for entry in request["requests"]}
    for artifact in result["artifacts"]:
        pair = artifact["item_id"], artifact["data_id"]
        spec_path = out_root / artifact["figure_spec_path"]
        png_path = out_root / artifact["rendered_asset_path"]
        display = result["display"]["|".join(pair)]
        svg_path = out_root / display["svg_path"]
        spec = json.loads(spec_path.read_text(encoding="utf-8"))

        assert spec["source_content"] == requests[pair]["source_content"]
        assert spec["request_sha256"] == canonical_sha256(request)
        assert spec["source_content_sha256"] == requests[pair]["source_content_sha256"]
        assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert svg_path.read_text(encoding="utf-8").startswith("<svg")
        assert display["png_path"] == artifact["rendered_asset_path"]
        assert display["width_mm"] <= 112
        assert display["height_mm"] > 0
        assert all(line in requests[pair]["source_content"].splitlines() for line in display["replace_lines"])
        with Image.open(png_path) as image:
            assert image.mode == "L"
            assert image.width <= 1323


def test_display_replaces_only_exact_diagram_rows(built):
    request, _, result = built
    by_pair = {(entry["item_id"], entry["data_id"]): entry for entry in request["requests"]}

    expected = {
        "FRG-SOC-2028-M01-Q03|DIARY-A": by_pair[("FRG-SOC-2028-M01-Q03", "DIARY-A")]["source_content"].splitlines()[1:3],
        "FRG-SOC-2028-M01-Q07|FLOW-A": by_pair[("FRG-SOC-2028-M01-Q07", "FLOW-A")]["source_content"].splitlines()[1:3],
        "FRG-SOC-2028-M01-Q08|CULTURE-A": by_pair[("FRG-SOC-2028-M01-Q08", "CULTURE-A")]["source_content"].splitlines()[1:2],
        "FRG-SOC-2028-M01-Q09|CRAFT-A": by_pair[("FRG-SOC-2028-M01-Q09", "CRAFT-A")]["source_content"].splitlines()[1:2],
        "FRG-SOC-2028-M01-Q11|LANGUAGE-A": by_pair[("FRG-SOC-2028-M01-Q11", "LANGUAGE-A")]["source_content"].splitlines()[1:4],
        "FRG-SOC-2028-M01-Q12|LAND-A": by_pair[("FRG-SOC-2028-M01-Q12", "LAND-A")]["source_content"].splitlines()[1:3],
        "FRG-SOC-2028-M01-Q13|WORK-A": by_pair[("FRG-SOC-2028-M01-Q13", "WORK-A")]["source_content"].splitlines()[1:5],
        "FRG-SOC-2028-M01-Q16|SHIFT-A": by_pair[("FRG-SOC-2028-M01-Q16", "SHIFT-A")]["source_content"].splitlines()[1:7],
        "FRG-SOC-2028-M01-Q19|INDEX-B": by_pair[("FRG-SOC-2028-M01-Q19", "INDEX-B")]["source_content"].splitlines()[2:6],
    }
    flood_lines = by_pair[("FRG-SOC-2028-M01-Q05", "FLOOD-A")]["source_content"].splitlines()
    expected["FRG-SOC-2028-M01-Q05|FLOOD-A"] = flood_lines[1:5] + flood_lines[6:10]

    for key, display in result["display"].items():
        assert display["replace_lines"] == expected.get(key, [])


def test_statistical_graph_specs_use_exact_source_values(built):
    _, out_root, result = built
    artifacts = {entry["data_id"]: entry for entry in result["artifacts"]}

    work = json.loads((out_root / artifacts["WORK-A"]["figure_spec_path"]).read_text(encoding="utf-8"))
    assert work["core_variables"]["series"] == [
        {"label": "A", "values": [120, 70, 30]},
        {"label": "B", "values": [100, 20, 10]},
        {"label": "C", "values": [110, 10, 10]},
    ]
    work_svg = (out_root / result["display"]["FRG-SOC-2028-M01-Q13|WORK-A"]["svg_path"]).read_text(
        encoding="utf-8"
    )
    assert ">대안</text>" in work_svg
    index = json.loads((out_root / artifacts["INDEX-B"]["figure_spec_path"]).read_text(encoding="utf-8"))
    assert index["core_variables"]["series"] == [
        {"label": "1차 명목임금", "values": [80]},
        {"label": "1차 생활물가", "values": [100]},
        {"label": "2차 명목임금", "values": [90]},
        {"label": "2차 생활물가", "values": [120]},
    ]


def test_map_and_layer_specs_encode_only_source_topology(built):
    _, out_root, result = built
    artifacts = {entry["data_id"]: entry for entry in result["artifacts"]}

    def variables(data_id):
        return json.loads(
            (out_root / artifacts[data_id]["figure_spec_path"]).read_text(encoding="utf-8")
        )["core_variables"]["topology"]

    assert variables("CULTURE-A") == {
        "type": "north_south_map",
        "nodes": [
            {"position": "북쪽", "text": "마루섬[H·●·도기판]", "tokens": ["H", "●", "도기판"]},
            {"position": "남쪽", "text": "노을섬[H·○·잎덮개]", "tokens": ["H", "○", "잎덮개"]},
        ],
        "connector": {"symbol": "━", "meaning": "남북 위치 연결 표시로 항로가 아님"},
    }
    assert variables("CRAFT-A") == {
        "type": "vertical_layers",
        "direction_label": "위에서 아래로",
        "layers": ["나층[T]", "라층[V]", "교역 개시 표지층", "가층[R]", "다층[S]"],
    }
    assert variables("LANGUAGE-A") == {
        "type": "west_east_language_grid",
        "direction": {"west": "서쪽", "east": "동쪽"},
        "districts": ["[다 생활권]", "[바 생활권]", "[사 생활권]"],
        "layers": [
            {"label": "주민 언어 층", "values": ["다=별말·솔말", "바=솔말·노을말", "사=노을말"]},
            {"label": "상담소 지원 언어 층", "values": ["다=별말·솔말", "바=솔말", "사=노을말"]},
        ],
    }
    assert variables("LAND-A") == {
        "type": "land_use_grid",
        "rows": [
            {"label": "기존 시가지", "cells": ["[가: 주택→업무]", "[나: 공장→업무]"]},
            {"label": "외곽", "cells": ["[다: 미개발→주택]", "[라: 주택→주택]"]},
        ],
    }


def test_rendered_map_primitives_keep_spatial_relations(built):
    _, out_root, result = built
    ns = {"svg": "http://www.w3.org/2000/svg"}

    def svg(data_id):
        key = next(key for key in result["display"] if key.endswith("|" + data_id))
        return ET.fromstring((out_root / result["display"][key]["svg_path"]).read_text(encoding="utf-8"))

    culture = svg("CULTURE-A")
    north = culture.find(".//svg:text[@data-node='north']", ns)
    south = culture.find(".//svg:text[@data-node='south']", ns)
    assert float(north.attrib["y"]) < float(south.attrib["y"])
    assert float(north.attrib["x"]) == float(south.attrib["x"])
    assert "━=남북 위치 연결 표시로 항로가 아님" in "".join(culture.itertext())

    craft = svg("CRAFT-A")
    layer_y = [float(craft.find(f".//svg:text[@data-layer='{index}']", ns).attrib["y"]) for index in range(5)]
    assert layer_y == sorted(layer_y)

    language = svg("LANGUAGE-A")
    district_x = [
        float(language.find(f".//svg:text[@data-district='{name}']", ns).attrib["x"])
        for name in ("다", "바", "사")
    ]
    assert district_x == sorted(district_x)
    assert len(language.findall(".//svg:text[@data-language-layer]", ns)) == 6

    land = svg("LAND-A")
    cells = {
        name: land.find(f".//svg:rect[@data-land-cell='{name}']", ns).attrib
        for name in ("가", "나", "다", "라")
    }
    assert cells["가"]["y"] == cells["나"]["y"]
    assert cells["다"]["y"] == cells["라"]["y"]
    assert cells["가"]["x"] == cells["다"]["x"]
    assert cells["나"]["x"] == cells["라"]["x"]
    assert cells["가"]["width"] == cells["나"]["width"] == cells["다"]["width"] == cells["라"]["width"]
    assert cells["가"]["height"] == cells["나"]["height"] == cells["다"]["height"] == cells["라"]["height"]


def test_statistical_bars_render_one_visible_cell_per_ten_units(built):
    _, out_root, result = built
    ns = {"svg": "http://www.w3.org/2000/svg"}

    def root(data_id):
        key = next(key for key in result["display"] if key.endswith("|" + data_id))
        return ET.fromstring(
            (out_root / result["display"][key]["svg_path"]).read_text(encoding="utf-8")
        )

    work = root("WORK-A")
    assert len(work.findall(".//svg:rect[@data-series='A'][@data-value='120']", ns)) == 12
    assert len(work.findall(".//svg:rect[@data-series='B'][@data-value='20']", ns)) == 2
    index = root("INDEX-B")
    assert len(index.findall(".//svg:rect[@data-series='1차 명목임금'][@data-value='80']", ns)) == 8
    assert len(index.findall(".//svg:rect[@data-series='2차 생활물가'][@data-value='120']", ns)) == 12


@pytest.mark.parametrize("failure", ["corrupt_png", "missing_spec"])
def test_forge_validator_rejects_corrupt_or_missing_asset(built, tmp_path, failure):
    request, out_root, result = built
    copied = tmp_path / "copy"
    shutil.copytree(out_root, copied)
    artifact = result["artifacts"][0]
    if failure == "corrupt_png":
        (copied / artifact["rendered_asset_path"]).write_bytes(b"corrupt")
        match = "VISUAL_FILE_SHA_MISMATCH"
    else:
        (copied / artifact["figure_spec_path"]).unlink()
        match = "VISUAL_FILE_UNREADABLE"

    with pytest.raises(VisualHandoffError, match=match):
        validate_visual_artifacts(
            request, copy.deepcopy(result["receipt"]), copy.deepcopy(result["artifacts"]), copied
        )


def test_rejects_fabricated_commit_and_stale_source(tmp_path):
    from press_visuals import VisualBuildError, build_visuals

    request = json.loads(HANDOFF.read_text(encoding="utf-8"))
    with pytest.raises(VisualBuildError, match="PRESS_COMMIT"):
        build_visuals(request, tmp_path / "bad-commit", "PASS")

    stale = copy.deepcopy(request)
    stale["requests"][0]["source_content"] += "변조"
    with pytest.raises(VisualBuildError, match="SOURCE_CONTENT_SHA256"):
        build_visuals(stale, tmp_path / "stale", "a" * 40)
