import copy
import importlib.util
import json
import zipfile
import hashlib
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
FORGE=ROOT.parent/'integrated-social-item-forge'
INPUT=ROOT.parent/'outputs/social-language-20260908'

def api():
    assert importlib.util.find_spec('press_revision') is not None, 'Revision ZIP input adapter is missing'
    import press_revision
    return press_revision

def source(campaign):
    return next(INPUT.glob('*'+campaign+'*.zip'))

@pytest.mark.parametrize('campaign,revision,expected,count',[
    ('M01','2026-09-08-language-r7','c62389a99b0fb1cc20ba39abe1f39124e8fe67db21bc3fece467202f102af459',13),
    ('M02','2026-09-08-language-r1','8dc9052caa1fda109f19073de6339cf8131c7b303c6e1c76d8e261039903624b',14)])
def test_revision_zip_preserves_corrected_source_and_pending_adjudication(campaign,revision,expected,count):
    m=api(); packet=m.load_revision(source(campaign),FORGE)
    items=json.loads(zipfile.ZipFile(source(campaign)).read('items.json'))
    assert packet['source_version']==revision
    assert packet['binding']['canonical_artifacts']['items_sha256']==expected
    assert [i['student_view'] for i in packet['items']]==[i['student_view'] for i in items]
    assert len(packet['items'])==25 and sum(i['points'] for i in packet['items'])==50
    assert packet['status']['content_status']=='NEEDS_ADJUDICATION'
    assert packet['status']['conditional_items']==count
    assert packet['human_release_approval'] is None
    assert packet['official_forge_export'] is False
    m.validate_revision(packet,source(campaign),FORGE)

def rewrite_zip(tmp_path,change,rebind=False):
    with zipfile.ZipFile(source('M01')) as z:
        members={n:z.read(n) for n in z.namelist()}
    change(members)
    if rebind:
        manifest=json.loads(members['delivery_manifest.json'])
        for f in manifest['files']:
            f['sha256']=hashlib.sha256(members[f['path']]).hexdigest()
            f['size']=len(members[f['path']])
        members['delivery_manifest.json']=json.dumps(manifest,ensure_ascii=False).encode()
    path=tmp_path/'changed.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name,data in members.items(): z.writestr(name,data)
    return path

def test_revision_changed_raw_member_is_rejected(tmp_path):
    m=api()
    path=rewrite_zip(tmp_path,lambda d:d.update({'items.json':d['items.json']+b'\n'}))
    with pytest.raises(ValueError,match='MEMBER_HASH'): m.load_revision(path,FORGE)

def test_revision_changed_content_cannot_borrow_old_review_even_with_rehashed_manifest(tmp_path):
    m=api()
    def change(d):
        items=json.loads(d['items.json']); items[0]['student_view']['choices'].reverse()
        d['items.json']=json.dumps(items,ensure_ascii=False).encode()
    path=rewrite_zip(tmp_path,change,True)
    with pytest.raises(ValueError,match='SOURCE_HASH|REVIEW'): m.load_revision(path,FORGE)

def test_revision_missing_review_is_rejected(tmp_path):
    m=api(); path=rewrite_zip(tmp_path,lambda d:d.pop('reviews/results/Q01/CONTENT.json'))
    with pytest.raises(ValueError,match='MEMBER_COVERAGE'): m.load_revision(path,FORGE)

def test_revision_zip_path_escape_is_rejected(tmp_path):
    m=api(); path=rewrite_zip(tmp_path,lambda d:d.update({'../escape.txt':b'bad'}))
    with pytest.raises(ValueError,match='UNSAFE'): m.load_revision(path,FORGE)

def test_revision_modified_packet_is_rejected():
    m=api(); packet=m.load_revision(source('M01'),FORGE)
    packet['items'][0]['student_view']['choices'].pop()
    with pytest.raises(ValueError,match='REVISION_PACKET_MISMATCH'): m.validate_revision(packet,source('M01'),FORGE)
