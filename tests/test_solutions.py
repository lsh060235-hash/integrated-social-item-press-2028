import copy
import importlib.util
import json
import zipfile

import pytest


def api():
    assert importlib.util.find_spec('press_solutions'), 'Source-bound solution editorial support is missing'
    import press_solutions
    return press_solutions


def fixture():
    packet = {'campaign_id': 'FRG-SOC-2028-M01', 'source_version': 'r1',
              'binding': {'canonical_artifacts': {'items_sha256': 'a'*64}},
              'items': [{'number': 1, 'points': 2, 'source_item_sha256': 'b'*64,
                         'student_view': {'prompt': '자료를 해석한 것은?', 'conditions': [],
                                          'choices': ['선택지']*5},
                         'teacher': {'answer': 2, 'rationale': 'INTERNAL_ONLY'}}]}
    overlay = {'schema_version': 'press-solutions-editorial-v0.1',
               'campaign_id': packet['campaign_id'], 'source_version': 'r1',
               'source_items_sha256': 'a'*64,
               'items': [{'number': 1, 'source_item_sha256': 'b'*64, 'answer': 2,
                          'topic': '자료의 해석', 'explanation': ['두 자료의 대상은 같다. 따라서 ②가 옳다.'],
                          'wrong_answers': [{'choice': n, 'text': '자료에서 확인할 수 없다.'}
                                            for n in [1, 3, 4, 5]]}]}
    return packet, overlay


def test_editorial_keeps_source_and_renders_only_revised_explanations(tmp_path):
    from press_layout import build_hwpx
    packet, overlay = fixture()
    before = copy.deepcopy(packet)
    edited = api().apply_editorial(packet, overlay)
    assert packet == before
    assert edited['items'][0]['teacher'] == before['items'][0]['teacher']
    assert edited['items'][0]['student_view'] == before['items'][0]['student_view']
    path = build_hwpx(edited, tmp_path/'solutions.hwpx', teacher=True)
    with zipfile.ZipFile(path) as z:
        xml = z.read('Contents/section0.xml').decode()
    assert '정답 해설' in xml and '오답피하기' in xml
    assert '자료의 해석' in xml and '두 자료의 대상은 같다.' in xml
    assert 'INTERNAL_ONLY' not in xml


@pytest.mark.parametrize('change', [
    lambda o: o.update(source_items_sha256='c'*64),
    lambda o: o.update(source_version='r2'),
    lambda o: o.update(campaign_id='FRG-SOC-2028-M02'),
    lambda o: o['items'][0].update(source_item_sha256='d'*64),
    lambda o: o['items'][0].update(answer=3),
    lambda o: o['items'].append(copy.deepcopy(o['items'][0])),
    lambda o: o['items'][0]['wrong_answers'].pop(),
    lambda o: o['items'][0]['wrong_answers'][0].update(choice=2),
    lambda o: o['items'][0]['wrong_answers'][0].update(text=''),
    lambda o: o['items'][0].update(explanation=[]),
    lambda o: o['items'][0].update(explanation=['[QUESTION-A]에서 VALUE_MATCH를 찾는다.']),
])
def test_rejects_stale_answers_missing_choices_and_internal_codes(change):
    packet, overlay = fixture()
    change(overlay)
    with pytest.raises(ValueError, match='SOLUTION_'):
        api().apply_editorial(packet, overlay)


def test_saved_editorial_cannot_change_after_build(tmp_path):
    from press_revision import verify_saved_plan
    from press_verify import sha
    (tmp_path/'visual-plan.json').write_text('{}')
    (tmp_path/'solution-editorial.json').write_text('{}')
    report = {'visual_plan_sha256': sha(tmp_path/'visual-plan.json'),
              'solution_editorial_sha256': sha(tmp_path/'solution-editorial.json')}
    (tmp_path/'verification.json').write_text(json.dumps(report))
    (tmp_path/'solution-editorial.json').write_text('{"changed":true}')
    with pytest.raises(ValueError, match='SOLUTION_EDITORIAL_CHANGED'):
        verify_saved_plan(tmp_path)
