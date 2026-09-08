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
        assert len(root.findall('.//hp:tbl',NS)) == 1
        assert root.find('.//hp:colPr[@colCount="2"]',NS) is not None
        assert not any('masterpage' in n for n in z.namelist())
        page=root.find('.//hp:pagePr',NS)
        assert page.get('landscape') == 'WIDELY', 'Matches native Hancom portrait blank'
        assert root.find('.//hp:secPr/hp:header',NS) is None, 'Headers are controls, not section properties'

def test_source_choices_not_silently_truncated(tmp_path):
    data=packet(); data['items'][0]['student_view']['choices'].pop()
    with pytest.raises(ValueError, match='CHOICES'):
        layout.build_hwpx(data,tmp_path/'bad.hwpx')
