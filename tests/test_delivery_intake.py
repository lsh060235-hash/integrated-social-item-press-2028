"""New aggregate deliveries retain evidence checks without borrowing older approvals."""
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from press_revision import load_revision, read_archive


def write_archive(path, members):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def bind(members):
    members['FILE_MANIFEST.json'] = json.dumps({
        n: hashlib.sha256(v).hexdigest() for n, v in members.items()
        if n != 'FILE_MANIFEST.json'
    }).encode()
    return members


def test_file_manifest_accepts_exact_coverage(tmp_path):
    members = bind({'data.json': b'{}'})
    assert read_archive(write_archive(tmp_path/'input.zip', members)) == members


@pytest.mark.parametrize('change, message', [
    ('bytes', 'MEMBER_HASH'), ('missing', 'MEMBER_COVERAGE'),
    ('extra', 'MEMBER_COVERAGE'), ('ambiguous', 'AMBIGUOUS')])
def test_file_manifest_rejects_changed_members(tmp_path, change, message):
    members = bind({'data.json': b'{}'})
    if change == 'bytes': members['data.json'] += b'\n'
    if change == 'missing': del members['data.json']
    if change == 'extra': members['extra.json'] = b'{}'
    if change == 'ambiguous': members['delivery_manifest.json'] = b'{}'
    with pytest.raises(ValueError, match=message):
        read_archive(write_archive(tmp_path/'input.zip', members))


ROOT = Path(__file__).resolve().parents[1]
FORGE = Path(os.environ.get('PRESS_FORGE_ROOT', ROOT.parent/'integrated-social-item-forge'))
INPUT = Path(os.environ.get('PRESS_DELIVERY_ROOT', FORGE/'deliveries/2026-09-08-language-v2'))
SOURCES = [('M01-language-v2-r1.zip', '2026-09-08-language-v2-r1', 19),
           ('M02-language-v2-r2.zip', '2026-09-08-language-v2-r2', 21),
           ('M03-new-higher-v4.zip', 'v4', 5)]


@pytest.mark.integration
@pytest.mark.parametrize('filename, version, conditional', SOURCES)
def test_aggregate_delivery_preserves_source_and_current_status(filename, version, conditional):
    path = INPUT/filename
    packet = load_revision(path, FORGE)
    with zipfile.ZipFile(path) as z:
        source = json.loads(z.read('items.json'))
        status = json.loads(z.read('DELIVERY_STATUS.json'))
    assert packet['source_version'] == version
    assert packet['status']['conditional_items'] == conditional
    assert packet['status']['blueprint_issue'] == status['blueprint_issue']
    assert packet['status']['content_status'] == status['review_collection_status']
    assert packet['human_release_approval'] is None
    assert packet['official_forge_export'] is False
    assert [i['student_view'] for i in packet['items']] == [i['student_view'] for i in source]
    assert [i['teacher']['answer'] for i in packet['items']] == [i['answer'] for i in source]
    assert packet['binding']['canonical_artifacts']['items_sha256'] == status['items_sha256']


@pytest.mark.integration
@pytest.mark.parametrize('target, message', [
    ('items.json', 'SOURCE_HASH'), ('reviews/review_packets.json', 'REVIEW_PACKET'),
    ('reviews/review_results.json', 'REVIEW_COLLECTION'),
    ('DELIVERY_STATUS.json', 'REVIEW_STATUS')])
def test_rehashed_aggregate_cannot_borrow_stale_evidence(tmp_path, target, message):
    with zipfile.ZipFile(INPUT/SOURCES[0][0]) as z:
        members = {n: z.read(n) for n in z.namelist()}
    data = json.loads(members[target])
    if target == 'items.json': data[0]['student_view']['choices'].reverse()
    if target == 'reviews/review_packets.json': data.pop()
    if target == 'reviews/review_results.json': data.pop()
    if target == 'DELIVERY_STATUS.json': data['role_verdicts']['CONTENT']['PASS'] = 25
    members[target] = json.dumps(data, ensure_ascii=False).encode()
    with pytest.raises(ValueError, match=message):
        load_revision(write_archive(tmp_path/'changed.zip', bind(members)), FORGE)
