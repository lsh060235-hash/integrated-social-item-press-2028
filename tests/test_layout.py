import os
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import pytest
import press_layout as layout

NS = {'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph'}

def packet():
    return {'campaign_id': 'FRG-SOC-TEST', 'items': [{'number': 1, 'points': 1.5,
        'item_id': 'FRG-SOC-TEST-Q01', 'student_view': {
            'prompt': '두 시점의 상태를 비교한 것으로 옳은 것은?',
            'conditions': [{'condition_id':'ARCHIVE-A', 'content': '출처: 가상 자료.\n| 시점 | 동편 | 서편 |\n| --- | --- | --- |\n| 2030년 | 허용 | 금지 |\n| 2032년 | 금지 | 허용 |\n동일한 두 구역이다.'}],
            'choices': ['변화 없음', '동편 변화', '서편 변화', '모두 폐쇄', '모두 허용']},
        'teacher': {'answer': 2, 'rationale': '비밀해설_SENTINEL'}}]}

def test_table_preserves_cells_and_surrounding_prose():
    blocks = layout.parse_material(packet()['items'][0]['student_view']['conditions'][0]['content'])
    assert blocks == [('text', '출처: 가상 자료.'), ('table', [['시점','동편','서편'],['2030년','허용','금지'],['2032년','금지','허용']]), ('text','동일한 두 구역이다.')]

def test_malformed_table_is_blocked_instead_of_losing_cells():
    with pytest.raises(ValueError, match='TABLE'):
        layout.parse_material('| 가 | 나 |\n| --- | --- |\n| 1 | 2 | 3 |')

def test_hwpx_is_editable_and_has_no_teacher_or_template_content(tmp_path):
    out = tmp_path/'exam.hwpx'
    layout.build_hwpx(packet(), out)
    with zipfile.ZipFile(out) as z:
        root = ET.fromstring(z.read('Contents/section0.xml'))
        text = ''.join(t.text or '' for t in root.findall('.//hp:t',NS))
        assert '두 시점의 상태를 비교한 것으로 옳은 것은?' in text
        assert '① 변화 없음' in text and '⑤ 모두 허용' in text
        assert '비밀해설_SENTINEL' not in text and 'ARCHIVE-A' not in text
        assert '과학탐구' not in text
        tables = root.findall('.//hp:tbl',NS)
        assert len(tables) == 2  # editable material frame plus nested data table
        frame = root.find('.//hp:tbl[@rowCnt="1"][@colCnt="1"]', NS)
        assert frame.find('.//hp:tbl[@rowCnt="3"]', NS) is not None
        assert '동일한 두 구역이다.' in ''.join(t.text or '' for t in frame.findall('.//hp:t', NS))
        assert root.find('.//hp:colPr[@colCount="2"]',NS) is not None
        assert not any('masterpage' in n for n in z.namelist())
        page=root.find('.//hp:pagePr',NS)
        assert page.get('landscape') == 'WIDELY', 'Matches native Hancom portrait blank'
        assert root.find('.//hp:secPr/hp:header',NS) is None, 'Headers are controls, not section properties'
        assert len(root.findall('.//hp:ctrl/hp:header//hp:line',NS))==2, 'Page rules must reach the native header control'

def test_source_choices_not_silently_truncated(tmp_path):
    data=packet(); data['items'][0]['student_view']['choices'].pop()
    with pytest.raises(ValueError, match='CHOICES'):
        layout.build_hwpx(data,tmp_path/'bad.hwpx')


def test_paired_choices_keep_every_original_token_in_row_order(tmp_path):
    data=packet()
    data['items'][0]['student_view']['choices']=['갑 P — 을 R','갑 Q — 을 P','갑 Q — 을 R','갑 R — 을 Q','갑 R — 을 P']
    out=tmp_path/'pairs.hwpx'; layout.build_hwpx(data,out)
    with zipfile.ZipFile(out) as z:
        root=ET.fromstring(z.read('Contents/section0.xml'))
        answer=root.find('.//hp:tbl[@rowCnt="5"][@colCnt="3"]',NS)
        assert answer is not None
        for index,row in enumerate(answer.findall('hp:tr',NS)):
            text=''.join(t.text or '' for t in row.findall('.//hp:t',NS))
            assert ''.join(text.split())==''.join((layout.CIRCLED[index]+data['items'][0]['student_view']['choices'][index]).split())

def test_revision_edition_is_visible_in_output(tmp_path):
    data=packet(); data['edition_label']='FRG-SOC-M01 · 표현교정 r7'
    out=tmp_path/'edition.hwpx'; layout.build_hwpx(data,out)
    with zipfile.ZipFile(out) as z:
        assert '표현교정 r7' in z.read('Contents/section0.xml').decode('utf-8')

@pytest.mark.integration
def test_additive_figure_insertion_keeps_native_source(tmp_path):
    import json
    import copy
    from press_contract import load_packet
    from press_visuals import build_visuals
    from press_verify import sha,validate_visual_result
    forge=Path(os.environ.get('PRESS_FORGE_ROOT', Path(__file__).resolve().parents[2]/'integrated-social-item-forge'))
    data=load_packet(forge,'FRG-SOC-2028-M01')
    figures=tmp_path/'figures'
    result=build_visuals(data['visual_handoff'],figures,'a'*40)
    key='FRG-SOC-2028-M01-Q02|SCENARIO-A'
    artifact=result['artifacts'][0]
    spec_path=figures/artifact['figure_spec_path']
    spec=json.loads(spec_path.read_text(encoding='utf-8'))
    line=spec['source_content'].splitlines()[0]
    spec['insert_before_line']=line
    spec_path.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
    result['receipt']['bindings'][0]['figure_spec_sha256']=sha(spec_path)
    result['display'][key]['insert_before_line']=line
    out=tmp_path/'additive.hwpx'
    layout.build_hwpx(data,out,[2],visuals=result,artifact_root=figures)
    with zipfile.ZipFile(out) as z:
        xml=ET.fromstring(z.read('Contents/section0.xml'))
        assert len(xml.findall('.//hp:pic',NS))==1
        assert line in ''.join(t.text or '' for t in xml.findall('.//hp:t',NS))
    changed=copy.deepcopy(result)
    changed['display'][key]['insert_before_line']='source does not contain this'
    with pytest.raises(ValueError,match='INSERTION'):
        validate_visual_result(data['visual_handoff'],changed,figures)
