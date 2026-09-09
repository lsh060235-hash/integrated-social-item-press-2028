import hashlib
import json
from pathlib import Path

import pytest

import press_visuals
from press_revision import visual_font_manifest


def write_config(path: Path, font_path: Path, digest: str) -> None:
    path.write_text(
        json.dumps(
            {
                "visual_fonts": {
                    "family": "SidaeAi",
                    "regular": {"path": str(font_path), "sha256": digest},
                }
            }
        ),
        encoding="utf-8",
    )


def test_configured_visual_font_resolves_path_family_and_hash(tmp_path):
    font_path = tmp_path / "SidaeAi-Regular.otf"
    font_path.write_bytes(b"test-font-bytes")
    digest = hashlib.sha256(font_path.read_bytes()).hexdigest()
    config_path = tmp_path / "config.local.json"
    write_config(config_path, font_path, digest)

    configured = press_visuals._configured_font("regular", config_path)

    assert configured == {
        "path": font_path.resolve(),
        "family": "SidaeAi",
        "style": "regular",
        "sha256": digest,
    }


def test_configured_visual_font_rejects_changed_file(tmp_path):
    font_path = tmp_path / "SidaeAi-Regular.otf"
    font_path.write_bytes(b"original")
    config_path = tmp_path / "config.local.json"
    write_config(config_path, font_path, hashlib.sha256(b"original").hexdigest())
    font_path.write_bytes(b"changed")

    with pytest.raises(press_visuals.VisualBuildError, match="VISUAL_FONT_SHA256_MISMATCH"):
        press_visuals._configured_font("regular", config_path)


def test_configured_visual_font_is_optional_when_local_config_has_no_font_section(tmp_path):
    config_path = tmp_path / "config.local.json"
    config_path.write_text("{}", encoding="utf-8")

    assert press_visuals._configured_font("regular", config_path) is None


@pytest.mark.parametrize(
    ("loaded_name", "error"),
    [
        (("SidaeAi", "Italic"), "VISUAL_FONT_STYLE_MISMATCH"),
        (("Different Family", "Regular"), "VISUAL_FONT_FAMILY_MISMATCH"),
    ],
)
def test_font_loader_rejects_internal_name_that_disagrees_with_config(
    monkeypatch, tmp_path, loaded_name, error
):
    class NamedFont:
        def getname(self):
            return loaded_name

    configured = {
        "path": tmp_path / "font.otf",
        "family": "SidaeAi",
        "style": "regular",
        "sha256": "0" * 64,
    }
    monkeypatch.setattr(press_visuals, "_configured_font", lambda style: configured)
    monkeypatch.setattr(press_visuals.ImageFont, "truetype", lambda path, size: NamedFont())

    with pytest.raises(press_visuals.VisualBuildError, match=error):
        press_visuals._font("regular")


def test_runtime_font_manifest_comes_from_pinned_visual_result():
    result = {
        "font_provenance": [
            {
                "name": "SidaeAi-Regular-3.1.otf",
                "family": "SidaeAi",
                "style": "regular",
                "sha256": "a" * 64,
                "purpose": "visuals",
            }
        ]
    }

    assert visual_font_manifest(result) == [
        {
            "name": "SidaeAi-Regular-3.1.otf",
            "family": "SidaeAi",
            "style": "regular",
            "sha256": "a" * 64,
            "purpose": "visuals",
        }
    ]
