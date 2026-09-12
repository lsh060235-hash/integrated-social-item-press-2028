"""The local editorial path must not manufacture reviewed-delivery evidence."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from press_editorial_draft import load_editorial_draft, read_editorial_archive


ROOT = Path(__file__).resolve().parents[1]
FORGE = ROOT.parent / 'integrated-social-item-forge'
DELIVERIES = FORGE / 'deliveries/2026-09-12-applied'


@pytest.mark.integration
@pytest.mark.parametrize('round_number,expected_hold', [(1, False), (2, True), (3, True), (4, True)])
def test_four_exact_editorial_archives_are_unapproved(round_number, expected_hold):
    archive = DELIVERIES / f'M{round_number:02d}-editorial-20260912-r1.zip'
    packet = load_editorial_draft(archive, FORGE)
    assert len(packet['items']) == 25
    assert sum(i['points'] for i in packet['items']) == 50
    assert packet['status']['press_status'] == 'DRAFT_FOR_HUMAN_REVIEW'
    assert packet['status']['input_integrity'] == 'PASS'
    assert packet['status']['content_status'] == 'NOT_REVIEWED'
    assert (packet['status']['blueprint_issue'] == 'CURRICULUM_COVERAGE') == expected_hold
    assert packet['status']['review_collection'] is None
    assert packet['human_release_approval'] is None
    assert packet['official_forge_export'] is False
    assert packet['binding']['source_zip_sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as z:
        students = json.loads(z.read('student_items.json'))
    assert [i['student_view'] for i in packet['items']] == [s['student_view'] for s in students]
    assert all('answer' not in s['student_view'] and 'rationale' not in s['student_view'] for s in students)


def mutate(tmp_path, change, *, rebind=False):
    archive = DELIVERIES / 'M04-editorial-20260912-r1.zip'
    with zipfile.ZipFile(archive) as z:
        members = {n: z.read(n) for n in z.namelist()}
    change(members)
    result = tmp_path / archive.name
    with zipfile.ZipFile(result, 'w') as z:
        for name, data in members.items():
            z.writestr(name, data)
    if not rebind:
        return result, None
    index = {'schema_version': 'press-editorial-draft-sources-v1', 'sources': {
        result.name: {'archive_sha256': hashlib.sha256(result.read_bytes()).hexdigest(),
                      'members': {n: hashlib.sha256(data).hexdigest() for n, data in members.items()}}}}
    return result, index


@pytest.mark.integration
def test_archive_byte_mutation_rejected_without_trusted_rebinding(tmp_path):
    path, _ = mutate(tmp_path, lambda d: d.update({'items.json': d['items.json'] + b'\n'}))
    with pytest.raises(ValueError, match='ARCHIVE_SHA_MISMATCH'):
        load_editorial_draft(path, FORGE)


@pytest.mark.integration
def test_student_view_mismatch_rejected_even_with_rebound_hashes(tmp_path):
    def change(members):
        students = json.loads(members['student_items.json'])
        students[0]['student_view']['choices'][0] = '변조된 선지'
        members['student_items.json'] = json.dumps(students, ensure_ascii=False).encode()
    path, trusted = mutate(tmp_path, change, rebind=True)
    with pytest.raises(ValueError, match='STUDENT_VIEW_MISMATCH'):
        load_editorial_draft(path, FORGE, trusted_sources=trusted)


@pytest.mark.integration
@pytest.mark.parametrize('target', ['answer', 'choices', 'points'])
def test_teacher_and_blueprint_inconsistency_rejected(tmp_path, target):
    def change(members):
        name = 'blueprint.json' if target == 'points' else 'items.json'
        data = json.loads(members[name])
        if target == 'answer': data[0]['answer'] = 6
        elif target == 'choices': data[0]['student_view']['choices'].pop()
        else: data['items'][0]['points'] = 1.5
        members[name] = json.dumps(data, ensure_ascii=False).encode()
    path, trusted = mutate(tmp_path, change, rebind=True)
    with pytest.raises(ValueError, match='SCHEMA|BLUEPRINT|ITEM_GATE|STUDENT_VIEW|ANSWER'):
        load_editorial_draft(path, FORGE, trusted_sources=trusted)


@pytest.mark.integration
def test_hold_cannot_be_marked_ready_by_untrusted_note(tmp_path):
    def change(members):
        members['READ_FIRST.md'] = b'READY FOR PUBLICATION'
    path, trusted = mutate(tmp_path, change, rebind=True)
    packet = load_editorial_draft(path, FORGE, trusted_sources=trusted)
    assert packet['status']['blueprint_issue'] == 'CURRICULUM_COVERAGE'
    assert packet['status']['press_status'] == 'DRAFT_FOR_HUMAN_REVIEW'


@pytest.mark.integration
def test_missing_member_rejected_even_with_rebound_hashes(tmp_path):
    path, trusted = mutate(tmp_path, lambda d: d.pop('student_items.json'), rebind=True)
    with pytest.raises(ValueError, match='MEMBER_COVERAGE'):
        load_editorial_draft(path, FORGE, trusted_sources=trusted)


@pytest.mark.parametrize('name', ['../escape.txt', 'C:/drive.txt', '/absolute.txt'])
def test_unsafe_member_name_rejected(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(name, b'x')
    with pytest.raises(ValueError, match='UNSAFE_ZIP_MEMBER'):
        read_editorial_archive(archive, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())


def test_duplicate_member_name_rejected(tmp_path):
    archive = tmp_path / 'duplicate.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('items.json', b'1')
        z.writestr('items.json', b'2')
    with pytest.raises(ValueError, match='DUPLICATE_ZIP_MEMBER'):
        read_editorial_archive(archive, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())


@pytest.mark.integration
def test_explicit_intake_kind_and_replay_reject_wrong_kind():
    from press_revision import load_input, validate_revision
    archive = DELIVERIES / 'M04-editorial-20260912-r1.zip'
    packet = load_input(archive, FORGE, input_kind='editorial-draft')
    validate_revision(packet, archive, FORGE, input_kind='editorial-draft')
    with pytest.raises(ValueError, match='AMBIGUOUS_OR_MISSING_MANIFEST'):
        load_input(archive, FORGE, input_kind='reviewed')
    with pytest.raises(ValueError, match='REVISION_PACKET_MISMATCH'):
        validate_revision(packet, archive, FORGE, input_kind='reviewed')


@pytest.mark.integration
def test_old_visual_plan_cannot_follow_changed_source():
    from press_visuals import compile_visual_plan, make_visual_plan
    from press_revision import load_input
    packet = load_input(DELIVERIES / 'M04-editorial-20260912-r1.zip', FORGE,
                        input_kind='editorial-draft')
    plan = make_visual_plan(packet['visual_handoff'])
    changed = json.loads(json.dumps(packet['visual_handoff']))
    changed['requests'][0]['source_content'] += ' 수정'
    changed['requests'][0]['source_content_sha256'] = hashlib.sha256(
        changed['requests'][0]['source_content'].encode()).hexdigest()
    with pytest.raises(ValueError, match='VISUAL_PLAN_STALE'):
        compile_visual_plan(changed, plan)


def test_explicit_answer_key_on_student_surface_is_rejected():
    from press_verify import student_surface_leaks
    assert student_surface_leaks('1. 다음 물음에 답하시오.\n정답 ③\n① 갑 ② 을 ③ 병 ④ 정 ⑤ 무')
    assert student_surface_leaks('1. 다음 물음에 답하시오.\n[오답피하기]')
    assert not student_surface_leaks('1. 다음 물음에 답하시오.\n정답을 고르시오.\n① 갑 ② 을 ③ 병 ④ 정 ⑤ 무')


def test_return_manifest_cannot_claim_ready_or_approval(tmp_path):
    from press_verify import make_manifest, verify_manifest
    (tmp_path / 'student.txt').write_text('draft', encoding='utf8')
    manifest = make_manifest(tmp_path, {'input_kind': 'editorial-draft'})
    verify_manifest(tmp_path, manifest)
    manifest['status'] = 'READY'
    with pytest.raises(ValueError, match='RETURN_STATUS_INVALID'):
        verify_manifest(tmp_path, manifest)
    manifest['status'] = 'DRAFT_FOR_HUMAN_REVIEW'
    manifest['human_release_approval'] = 'approved'
    with pytest.raises(ValueError, match='RETURN_STATUS_INVALID'):
        verify_manifest(tmp_path, manifest)
