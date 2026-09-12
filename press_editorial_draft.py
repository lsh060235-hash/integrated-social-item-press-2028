"""Exact-source local intake for Forge editorial ZIPs without review evidence."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

from press_contract import ContractError, _forge_api


ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'profiles/editorial-draft-sources.json'
REQUIRED = {'items.json', 'item_specs.json', 'blueprint.json', 'student_items.json'}
SPEC_FIELDS = ('item_spec_id', 'curriculum_refs', 'item_type', 'data_grammar', 'difficulty_devices')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def read_editorial_archive(archive, *, expected_sha256, expected_members=None):
    """Read only a pinned ZIP; never execute embedded scripts or extract paths."""
    archive = Path(archive)
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ContractError('DUPLICATE_ZIP_MEMBER')
        if len(names) > 50:
            raise ContractError('EDITORIAL_MEMBER_COUNT')
        if sum(info.file_size for info in infos) > 50_000_000:
            raise ContractError('EDITORIAL_ARCHIVE_TOO_LARGE')
        for info in infos:
            name = info.filename
            mode = (info.external_attr >> 16) & 0o170000
            if (not name or info.is_dir() or mode == stat.S_IFLNK or
                any(c in name for c in ('\\', ':', '\x00')) or
                any(part in ('', '.', '..') for part in name.split('/')) or
                name.startswith('/')):
                raise ContractError('UNSAFE_ZIP_MEMBER')
            if info.file_size > 10_000_000:
                raise ContractError('EDITORIAL_MEMBER_TOO_LARGE')
        if not REQUIRED <= set(names):
            raise ContractError('MEMBER_COVERAGE_MISMATCH')
        if expected_members is not None and set(names) != set(expected_members):
            raise ContractError('MEMBER_COVERAGE_MISMATCH')
        if _sha(archive.read_bytes()) != expected_sha256:
            raise ContractError('ARCHIVE_SHA_MISMATCH')
        members = {name: source.read(name) for name in names}
    if expected_members is not None:
        for name, data in members.items():
            if _sha(data) != expected_members[name]:
                raise ContractError('MEMBER_SHA_MISMATCH: ' + name)
    return members


def load_editorial_draft(archive, forge_root, *, trusted_sources=None):
    """Create a Press-only, unreviewed packet from four bound JSON artifacts."""
    archive = Path(archive)
    profile = (trusted_sources if trusted_sources is not None else
               json.loads(SOURCES.read_text(encoding='utf-8')))
    if profile.get('schema_version') != 'press-editorial-draft-sources-v1':
        raise ContractError('EDITORIAL_SOURCE_PROFILE_INVALID')
    trusted = profile.get('sources', {}).get(archive.name)
    if not trusted or not re.fullmatch(r'M0[1-4]-editorial-20260912-r1\.zip', archive.name):
        raise ContractError('EDITORIAL_SOURCE_NOT_PINNED')
    members = read_editorial_archive(archive,
        expected_sha256=trusted['archive_sha256'], expected_members=trusted['members'])
    def get(name):
        try:
            return json.loads(members[name])
        except (KeyError, ValueError) as exc:
            raise ContractError('EDITORIAL_JSON_INVALID: ' + name) from exc

    items, specs, blueprint, students = (get(name) for name in
        ('items.json', 'item_specs.json', 'blueprint.json', 'student_items.json'))
    campaign = 'FRG-SOC-2028-' + archive.name[:3]
    if (blueprint.get('campaign_id') != campaign or blueprint.get('subject') != '통합사회'
        or blueprint.get('set_kind') != 'FULL' or blueprint.get('item_count') != 25
        or blueprint.get('total_points') != 50 or
        any(not isinstance(value, list) or len(value) != 25 for value in (items, specs, students))):
        raise ContractError('EDITORIAL_IDENTITY_MISMATCH')

    _, build_visual_handoff, canonical_sha256 = _forge_api(Path(forge_root))
    from integrated_social_forge.gates import run_gates
    from integrated_social_forge.lineage import validate_blueprint, validate_lineage
    from integrated_social_forge.validate import validate_payload

    schemas = {name: json.loads((Path(forge_root)/'schemas'/f'{name}.schema.json').read_text(encoding='utf-8'))
               for name in ('item', 'item_spec', 'blueprint')}
    try:
        validate_payload(blueprint, schema=schemas['blueprint'])
        for item, spec in zip(items, specs, strict=True):
            validate_payload(item, schema=schemas['item'])
            validate_payload(spec, schema=schemas['item_spec'])
            validate_lineage(spec)
    except ValueError as exc:
        raise ContractError('EDITORIAL_SCHEMA_INVALID: ' + str(exc)) from exc
    try:
        validate_blueprint(blueprint)
        blueprint_issue = None
    except ValueError as exc:
        if not str(exc).startswith('CURRICULUM_COVERAGE:'):
            raise ContractError('EDITORIAL_BLUEPRINT_INVALID: ' + str(exc)) from exc
        blueprint_issue = 'CURRICULUM_COVERAGE'

    by_spec = {s['item_spec_id']: s for s in specs}
    if len(by_spec) != 25 or set(by_spec) != {bp['item_spec_id'] for bp in blueprint['items']}:
        raise ContractError('EDITORIAL_DUPLICATE_SPEC')
    entries = []
    for number, (item, student, bp) in enumerate(zip(items, students, blueprint['items'], strict=True), 1):
        item_id = f'{campaign}-Q{number:02d}'
        spec = by_spec.get(bp['item_spec_id'])
        if (bp['item_no'] != number or item['item_id'] != item_id or
            item['item_spec_id'] != bp['item_spec_id'] or spec is None or
            any(bp[field] != spec[field] for field in SPEC_FIELDS) or
            set(student) != {'item_no', 'item_id', 'points', 'student_view'} or
            student['item_no'] != number or student['item_id'] != item_id or
            student['points'] != bp['points'] or
            item['student_view'] != student['student_view']):
            raise ContractError('STUDENT_VIEW_MISMATCH: ' + item_id)
        if (item['answer'] not in range(1, 6) or
            len(student['student_view']['choices']) != 5 or
            len(item['choice_evaluations']) != 5):
            raise ContractError('ANSWER_OR_CHOICES_INVALID: ' + item_id)
        gate = run_gates(item, item_spec=spec)
        if gate['status'] != 'PASS':
            raise ContractError('EDITORIAL_ITEM_GATE: ' + item_id + ': ' + repr(gate['errors']))
        entries.append({'number': number, 'points': bp['points'], 'item_id': item_id,
            'source_item_sha256': canonical_sha256(item), 'item_revision': archive.stem,
            'student_view': student['student_view'],
            'teacher': {key: item[key] for key in ('answer', 'rationale', 'solution_steps', 'choice_evaluations')},
            'materials': item['materials'], 'core_data_relations': spec['core_data_relations']})

    if sum(e['points'] for e in entries) != 50:
        raise ContractError('EDITORIAL_POINTS_MISMATCH')
    visual = build_visual_handoff(items, specs, campaign_id=campaign)
    support_file = Path(forge_root)/'data/contracts/press_support.json'
    support = json.loads(support_file.read_text(encoding='utf-8'))
    if (support.get('subject') != '통합사회' or
        support.get('press_contract_version') != '1.1' or
        support.get('status') != 'UNSUPPORTED' or
        support.get('code') != 'PRESS_CONTRACT_UNSUPPORTED_SUBJECT' or
        support.get('contract_approval') is not None):
        raise ContractError('FORGE_SUPPORT_EVIDENCE_INVALID')
    notes = profile.get('manual_review_notes', {}).get(campaign, [])
    canonical = {name+'_sha256': canonical_sha256(value) for name, value in
                 (('items', items), ('item_specs', specs), ('blueprint', blueprint), ('student_items', students))}
    source_version = archive.stem.removeprefix(campaign[-3:]+'-')
    return {'schema_version': 'integrated-social-press-revision-input-v0.1',
        'campaign_id': campaign, 'subject': '통합사회', 'curriculum_revision': '2022',
        'source_version': source_version,
        'edition_label': f'제{int(campaign[-2:])}회 · 편집 검토 초안',
        'official_forge_export': False, 'human_release_approval': None,
        'status': {'content_status': 'NOT_REVIEWED', 'conditional_items': None,
            'human_approval': None, 'blueprint_issue': blueprint_issue,
            'press_status': 'DRAFT_FOR_HUMAN_REVIEW', 'input_integrity': 'PASS',
            'review_collection': None, 'manual_review_notes': notes,
            'official_forge_press_contract': support['status'],
            'visual_semantic_review': 'PENDING'},
        'items': entries, 'visual_handoff': visual,
        'binding': {'hash_algorithm': 'SHA-256', 'canonical_artifacts': canonical,
            'input_kind': 'editorial-draft', 'source_zip_sha256': trusted['archive_sha256'],
            'source_version': source_version, 'source_zip_filename': archive.name,
            'visual_handoff_sha256': canonical_sha256(visual),
            'forge_press_support_sha256': _sha(support_file.read_bytes()),
            'files': [{'path': name, 'sha256': _sha(data)} for name, data in sorted(members.items())]}}
