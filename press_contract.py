"""Read-only Forge adapter for the local Integrated Social Press draft."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


sys.dont_write_bytecode = True
_SCHEMA_PATH = Path(__file__).with_name("schemas") / "press_input_v0.1.schema.json"
_CAMPAIGN_ID = re.compile(r"FRG-SOC-[A-Z0-9-]+")


class ContractError(ValueError):
    """The Forge source or supplied packet does not satisfy this contract."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"SOURCE_UNREADABLE: {path}: {exc}") from exc


def _forge_api(forge_root: Path):
    source = forge_root / "src"
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        from integrated_social_forge.campaign_status import build_campaign_status
        from integrated_social_forge.canonical import canonical_sha256
        from integrated_social_forge.visual_handoff import build_visual_handoff
    except ImportError as exc:
        raise ContractError(f"FORGE_API_UNAVAILABLE: {source}") from exc
    return build_campaign_status, build_visual_handoff, canonical_sha256


def _schema_validate(packet: dict[str, Any]) -> None:
    try:
        Draft202012Validator(_load(_SCHEMA_PATH)).validate(packet)
    except Exception as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"PACKET_SCHEMA_INVALID: {exc}") from exc


def _current_packet_manifest(campaign: Path, items_sha: str, specs_sha: str) -> Path:
    current = []
    for path in sorted((campaign / "reviews").glob("*/packets/manifest.json")):
        manifest = _load(path)
        if (
            isinstance(manifest, dict)
            and manifest.get("source_items_sha256") == items_sha
            and manifest.get("source_item_specs_sha256") == specs_sha
        ):
            current.append(path)
    if not current:
        raise ContractError("CURRENT_REVIEW_PACKETS_MISSING")
    return current[-1]


def _binding_paths(
    forge_root: Path, campaign: Path, items_sha: str, specs_sha: str
) -> list[Path]:
    manifest_path = _current_packet_manifest(campaign, items_sha, specs_sha)
    manifest = _load(manifest_path)
    paths = [
        forge_root / "data" / "contracts" / "press_support.json",
        campaign / "blueprint.json",
        campaign / "item_specs.json",
        campaign / "items.json",
        campaign / "validation_report.json",
        campaign / "reviews" / "final" / "collection_report.json",
        campaign / "reviews" / "final" / "human_approval_request.json",
        campaign / "approvals" / "receipt.json",
        manifest_path,
    ]
    paths.extend(manifest_path.parent / entry["file"] for entry in manifest["packets"])
    paths.extend(sorted((campaign / "reviews" / "final" / "results").glob("*/*.json")))
    paths.extend(sorted(path for path in (campaign / "approvals").glob("Q*.json")))
    return paths


def _file_bindings(forge_root: Path, paths: list[Path]) -> list[dict[str, str]]:
    root = forge_root.resolve(strict=True)
    bindings = []
    for path in paths:
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise ContractError(f"UNSAFE_SOURCE_PATH: {path}")
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractError(f"SOURCE_UNREADABLE: {path}: {exc}") from exc
        bindings.append({"path": resolved.relative_to(root).as_posix(), "sha256": digest})
    if len(bindings) != len({entry["path"] for entry in bindings}):
        raise ContractError("DUPLICATE_SOURCE_BINDING")
    return sorted(bindings, key=lambda entry: entry["path"])


def load_packet(forge_root: Path, campaign_id: str) -> dict:
    """Build a local Press packet from current, approved Forge evidence."""

    if not isinstance(campaign_id, str) or _CAMPAIGN_ID.fullmatch(campaign_id) is None:
        raise ContractError("INVALID_CAMPAIGN_ID")
    try:
        root = Path(forge_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ContractError(f"FORGE_ROOT_UNREADABLE: {forge_root}") from exc
    campaign = root / "campaigns" / campaign_id
    build_status, build_visual_handoff, canonical_sha256 = _forge_api(root)

    blueprint = _load(campaign / "blueprint.json")
    items = _load(campaign / "items.json")
    specs = _load(campaign / "item_specs.json")
    support = _load(root / "data" / "contracts" / "press_support.json")
    try:
        status = build_status(campaign, support)
        visual_handoff = build_visual_handoff(items, specs, campaign_id=campaign_id)
    except Exception as exc:
        raise ContractError(f"FORGE_CURRENT_EVIDENCE_INVALID: {exc}") from exc

    if (
        blueprint.get("campaign_id") != campaign_id
        or blueprint.get("subject") != "통합사회"
        or status.get("content_status") != "APPROVED"
        or len(items) != 25
        or len(specs) != 25
        or len(blueprint.get("items", [])) != 25
    ):
        raise ContractError("CAMPAIGN_CONTRACT_MISMATCH")

    specs_by_id = {spec.get("item_spec_id"): spec for spec in specs}
    entries = []
    for source, plan in zip(items, blueprint["items"], strict=True):
        spec = specs_by_id.get(source.get("item_spec_id"))
        if (
            spec is None
            or plan.get("item_spec_id") != source.get("item_spec_id")
            or source.get("item_id") != f"{campaign_id}-Q{plan.get('item_no', 0):02d}"
        ):
            raise ContractError("ITEM_BLUEPRINT_SPEC_MISMATCH")
        source_hash = canonical_sha256(source)
        entries.append(
            {
                "number": plan["item_no"],
                "points": plan["points"],
                "item_id": source["item_id"],
                "source_item_sha256": source_hash,
                "item_revision": source.get("item_version", source.get("version", source_hash)),
                "student_view": deepcopy(source["student_view"]),
                "teacher": {
                    "answer": source["answer"],
                    "rationale": source["rationale"],
                    "solution_steps": deepcopy(source["solution_steps"]),
                    "choice_evaluations": deepcopy(source["choice_evaluations"]),
                },
                "materials": deepcopy(source["materials"]),
                "core_data_relations": deepcopy(spec["core_data_relations"]),
            }
        )

    files = _file_bindings(
        root,
        _binding_paths(root, campaign, status["artifacts"]["items_sha256"], status["artifacts"]["item_specs_sha256"]),
    )
    packet = {
        "schema_version": "integrated-social-press-input-v0.1",
        "campaign_id": campaign_id,
        "subject": "통합사회",
        "curriculum_revision": "2022",
        "official_forge_export": False,
        "status": deepcopy(status),
        "items": entries,
        "visual_handoff": deepcopy(visual_handoff),
        "binding": {
            "hash_algorithm": "SHA-256",
            "canonical_artifacts": deepcopy(status["artifacts"]),
            "campaign_status_sha256": canonical_sha256(status),
            "visual_handoff_sha256": canonical_sha256(visual_handoff),
            "files": files,
        },
    }
    _schema_validate(packet)
    return packet


def validate_packet(packet: dict, forge_root: Path) -> None:
    """Reject altered packets and packets no longer matching current Forge bytes."""

    if not isinstance(packet, dict):
        raise ContractError("PACKET_SCHEMA_INVALID: packet must be an object")
    _schema_validate(packet)
    try:
        current = load_packet(forge_root, packet["campaign_id"])
    except ContractError as exc:
        raise ContractError(f"PACKET_SOURCE_MISMATCH: {exc}") from exc
    if packet != current:
        raise ContractError("PACKET_SOURCE_MISMATCH")
