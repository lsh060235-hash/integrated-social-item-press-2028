import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
ROOT = Path(__file__).parents[1]
FORGE = ROOT.parent / "integrated-social-item-forge"
sys.path.insert(0, str(FORGE / "src"))

from integrated_social_forge.canonical import canonical_sha256
from press_contract import ContractError, load_packet, validate_packet


CAMPAIGN_ID = "FRG-SOC-2028-M01"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def forge_copy(tmp_path: Path) -> Path:
    target = tmp_path / "forge"
    shutil.copytree(FORGE / "campaigns" / CAMPAIGN_ID, target / "campaigns" / CAMPAIGN_ID)
    support = target / "data" / "contracts" / "press_support.json"
    support.parent.mkdir(parents=True)
    shutil.copy2(FORGE / "data" / "contracts" / "press_support.json", support)
    return target


def test_packet_preserves_approved_source_and_unsupported_press_status():
    packet = load_packet(FORGE, CAMPAIGN_ID)
    campaign = FORGE / "campaigns" / CAMPAIGN_ID
    source_items = _load(campaign / "items.json")
    source_specs = _load(campaign / "item_specs.json")
    blueprint = _load(campaign / "blueprint.json")

    Draft202012Validator(_load(ROOT / "schemas" / "press_input_v0.1.schema.json")).validate(packet)
    assert packet["schema_version"] == "integrated-social-press-input-v0.1"
    assert packet["campaign_id"] == CAMPAIGN_ID
    assert packet["subject"] == "통합사회"
    assert packet["curriculum_revision"] == "2022"
    assert packet["official_forge_export"] is False
    assert packet["status"]["content_status"] == "APPROVED"
    assert packet["status"]["press_status"] == "HOLD"
    assert packet["status"]["press"]["code"] == "PRESS_CONTRACT_UNSUPPORTED_SUBJECT"
    assert len(packet["items"]) == 25
    assert len(packet["visual_handoff"]["requests"]) == 18

    specs = {spec["item_spec_id"]: spec for spec in source_specs}
    for source, entry, plan in zip(source_items, packet["items"], blueprint["items"], strict=True):
        source_hash = canonical_sha256(source)
        assert entry == {
            "number": plan["item_no"],
            "points": plan["points"],
            "item_id": source["item_id"],
            "source_item_sha256": source_hash,
            "item_revision": source.get("item_version", source.get("version", source_hash)),
            "student_view": source["student_view"],
            "teacher": {
                "answer": source["answer"],
                "rationale": source["rationale"],
                "solution_steps": source["solution_steps"],
                "choice_evaluations": source["choice_evaluations"],
            },
            "materials": source["materials"],
            "core_data_relations": specs[source["item_spec_id"]]["core_data_relations"],
        }

    bound = {entry["path"]: entry["sha256"] for entry in packet["binding"]["files"]}
    assert bound["campaigns/FRG-SOC-2028-M01/items.json"] == hashlib.sha256(
        (campaign / "items.json").read_bytes()
    ).hexdigest()
    assert "campaigns/FRG-SOC-2028-M01/reviews/round-03/packets/Q01/CONTENT.json" in bound
    assert "campaigns/FRG-SOC-2028-M01/reviews/final/results/CONTENT/Q01.json" in bound
    assert "campaigns/FRG-SOC-2028-M01/approvals/Q01.json" in bound
    validate_packet(packet, FORGE)


@pytest.mark.parametrize(
    ("relative", "mutate"),
    [
        ("items.json", lambda value: value[0]["student_view"]["choices"].pop()),
        ("item_specs.json", lambda value: value[0]["core_data_relations"].append("변조")),
        ("blueprint.json", lambda value: value.update(subject="변조")),
        (
            "reviews/final/results/CONTENT/Q01.json",
            lambda value: value.update(reviewer_id="tampered-reviewer"),
        ),
        ("approvals/Q01.json", lambda value: value.update(decision="FAIL")),
    ],
    ids=["missing-choice", "stale-spec", "stale-blueprint", "changed-review", "changed-approval"],
)
def test_actual_forge_source_defects_are_rejected(forge_copy: Path, relative, mutate):
    path = forge_copy / "campaigns" / CAMPAIGN_ID / relative
    value = _load(path)
    mutate(value)
    _write(path, value)

    with pytest.raises(ContractError):
        load_packet(forge_copy, CAMPAIGN_ID)


def test_packet_modification_or_choice_omission_is_rejected(forge_copy: Path):
    packet = load_packet(forge_copy, CAMPAIGN_ID)
    packet["items"][0]["student_view"]["choices"].pop()

    with pytest.raises(ContractError):
        validate_packet(packet, forge_copy)


def test_packet_becomes_stale_when_actual_source_changes(forge_copy: Path):
    packet = load_packet(forge_copy, CAMPAIGN_ID)
    source = forge_copy / "campaigns" / CAMPAIGN_ID / "items.json"
    items = _load(source)
    items[0]["student_view"]["prompt"] += " 변조"
    _write(source, items)

    with pytest.raises(ContractError):
        validate_packet(packet, forge_copy)


def test_packet_binding_rejects_raw_byte_change_even_when_json_is_equal(forge_copy: Path):
    packet = load_packet(forge_copy, CAMPAIGN_ID)
    source = forge_copy / "campaigns" / CAMPAIGN_ID / "items.json"
    source.write_bytes(source.read_bytes() + b"\n")

    with pytest.raises(ContractError, match="PACKET_SOURCE_MISMATCH"):
        validate_packet(packet, forge_copy)
