"""Portable regressions: synthetic inputs only, no Forge checkout or Hancom."""
import copy
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile

import fitz
import pytest

import press_layout as layout
import press_verify as verify
import press_visuals as visuals
from test_layout import packet, NS


def test_short_choices_use_one_row_without_changing_order(tmp_path):
    data = packet()
    choices = ['갑', '을', '병', '해당 대안 없음', '정']
    data['items'][0]['student_view']['choices'] = choices
    path = layout.build_hwpx(data, tmp_path / 'compact.hwpx')
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('Contents/section0.xml'))
    row = root.find('.//hp:tbl[@rowCnt="1"][@colCnt="5"]/hp:tr', NS)
    assert row is not None, 'Short choices should fit across a column'
    assert [''.join(t.text or '' for t in c.findall('.//hp:t', NS))
            for c in row] == [m + ' ' + c for m, c in zip(layout.CIRCLED, choices)]


def request():
    content = '설명\n| 시점 | 값 |\n| 2030 | 10 |'
    return {'campaign_id': 'FRG-SOC-2028-M03', 'requests': [{
        'item_id': 'FRG-SOC-2028-M03-Q01', 'data_id': 'DATA-A',
        'source_content': content,
        'source_content_sha256': hashlib.sha256(content.encode()).hexdigest()}]}


def test_visual_plan_accepts_new_campaign_and_rejects_stale_or_reordered_lines():
    source = request()
    plan = {'schema_version': 'press-visual-plan-v1', 'figures': [{
        'item_id': source['requests'][0]['item_id'], 'data_id': 'DATA-A',
        'source_content_sha256': source['requests'][0]['source_content_sha256'],
        'mode': 'table', 'lines': ['| 시점 | 값 |', '| 2030 | 10 |'], 'replace': False}]}
    compile_plan = getattr(visuals, 'compile_visual_plan', None)
    assert callable(compile_plan), 'A source-bound external visual plan is required'
    rules = compile_plan(source, plan)
    assert rules[('FRG-SOC-2028-M03-Q01', 'DATA-A')] == ('table', (1, 2), False)
    changed = copy.deepcopy(plan)
    changed['figures'][0]['source_content_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='STALE'):
        compile_plan(source, changed)
    changed = copy.deepcopy(plan)
    changed['figures'][0]['lines'].reverse()
    with pytest.raises(ValueError, match='ORDER'):
        compile_plan(source, changed)
    changed = copy.deepcopy(plan)
    changed['figures'].append(changed['figures'][0])
    with pytest.raises(ValueError, match='COVERAGE'):
        compile_plan(source, changed)


def synthetic_pdf(path, split=False):
    data = packet()
    sv = data['items'][0]['student_view']
    sv.update(prompt='Choose the answer.', conditions=[], choices=['A', 'B', 'C', 'D', 'E'])
    doc = fitz.open()
    page = doc.new_page(width=842, height=1189)
    page.insert_font(fontname='cjk', fontbuffer=fitz.Font('cjk').buffer)
    page.insert_text((90, 250), '1. Choose the answer. [1.5점]', fontname='cjk')
    for n, choice in enumerate(sv['choices']):
        page.insert_text((470 if split and n == 4 else 90, 300 + n * 30),
                         layout.CIRCLED[n] + ' ' + choice, fontname='cjk')
    doc.save(path)
    doc.close()
    return data


def test_exam_verifier_fails_when_last_choice_moves_to_other_column(tmp_path):
    pdf = tmp_path / 'split.pdf'
    data = synthetic_pdf(pdf, split=True)
    hwpx = layout.build_hwpx(data, tmp_path / 'split.hwpx')
    report = verify.verify_exam(data, hwpx, pdf, {}, tmp_path)
    assert 'ITEM_SPLIT_ACROSS_COLUMNS: 1' in report['errors']


def test_item_review_crops_are_bound_to_pdf_and_cover_every_item(tmp_path):
    pdf = tmp_path / 'source.pdf'
    data = synthetic_pdf(pdf)
    build_review = getattr(verify, 'build_item_review', None)
    assert callable(build_review), 'The normal build must produce per-item review crops'
    report = build_review(data, pdf, tmp_path / 'review')
    assert report['pdf_sha256'] == verify.sha(pdf)
    assert [x['number'] for x in report['items']] == [1]
    assert report['items'][0]['status'] == 'PENDING'
    assert report['items'][0]['height_pt'] > 160
    assert (tmp_path / 'review' / report['items'][0]['image']).is_file()
    assert (tmp_path / 'review/index.html').is_file()


def test_final_column_balance_uses_geometry_instead_of_campaign_number():
    rows=[{'number':24,'page':8,'column':1,'whole_item_same_column':True},
          {'number':25,'page':8,'column':1,'whole_item_same_column':True}]
    assert verify.balance_last_column(rows)==(25,)
    rows[-1]['column']=2
    assert verify.balance_last_column(rows)==()
    assert verify.balance_last_column(rows[:1])==()


def test_unknown_visual_plan_does_not_guess_a_diagram_or_reuse_old_indices():
    source=request()
    exported=visuals.make_visual_plan(source)
    assert exported['figures'][0]['mode'] is None
    with pytest.raises(ValueError,match='MODE_REQUIRED'):
        visuals.compile_visual_plan(source,exported)


def test_new_review_requires_all_items_and_current_pdf(tmp_path):
    pdf=tmp_path/'source.pdf'
    data=synthetic_pdf(pdf)
    page_review={'exam_pdf_sha256':verify.sha(pdf),'exam_pages_reviewed':[1],
                 'item_numbers_reviewed':[]}
    check=getattr(verify,'validate_item_review',None)
    assert callable(check), 'Sealing must require explicit item review coverage'
    with pytest.raises(ValueError,match='ITEM_REVIEW'):
        check(data,pdf,page_review)
    page_review['item_numbers_reviewed']=[1]
    check(data,pdf,page_review)
    page_review['exam_pdf_sha256']='0'*64
    with pytest.raises(ValueError,match='STALE'):
        check(data,pdf,page_review)


def test_specialized_energy_chart_rejects_a_new_currency_source():
    source=request()
    plan=visuals.make_visual_plan(source)
    plan['figures'][0].update(mode='revision_work_bars',
        lines=source['requests'][0]['source_content'].splitlines()[1:],replace=True)
    with pytest.raises(ValueError,match='AUDITED_SOURCE'):
        visuals.compile_visual_plan(source,plan)


def test_ambiguous_source_lines_require_an_explicit_occurrence():
    source=request()
    entry=source['requests'][0]
    entry['source_content']='표\n| 가 | 나 |\n표\n| 다 | 라 |'
    entry['source_content_sha256']=hashlib.sha256(entry['source_content'].encode()).hexdigest()
    plan=visuals.make_visual_plan(source)
    plan['figures'][0].update(mode='table',lines=['표','| 다 | 라 |'])
    with pytest.raises(ValueError,match='AMBIGUOUS'):
        visuals.compile_visual_plan(source,plan)
    plan['figures'][0]['lines'][0]={'text':'표','occurrence':1}
    assert next(iter(visuals.compile_visual_plan(source,plan).values()))[1]==(2,3)


def test_sealed_plan_must_match_the_build_hash(tmp_path):
    import press_revision as revision
    path=tmp_path/'visual-plan.json';path.write_text('{}',encoding='utf-8')
    runtime=tmp_path/'runtime.json';runtime.write_text('{}',encoding='utf-8')
    check=getattr(revision,'verify_saved_plan',None)
    assert callable(check)
    (tmp_path/'verification.json').write_text(json.dumps({
        'visual_plan_sha256':verify.sha(path),
        'reproduction_files':verify.make_file_binding(tmp_path,[runtime]),
    }))
    check(tmp_path)
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='VISUAL_PLAN_CHANGED'):
        check(tmp_path)


def test_seal_rejects_changed_build_reproduction(tmp_path):
    import press_revision as revision
    plan=tmp_path/'visual-plan.json';plan.write_text('{}',encoding='utf-8')
    runtime=tmp_path/'runtime.json';runtime.write_text('{"press_commit":"abc"}',encoding='utf-8')
    source=tmp_path/'reproduction'/'press.py';source.parent.mkdir();source.write_text('original',encoding='utf-8')
    (tmp_path/'verification.json').write_text(json.dumps({
        'visual_plan_sha256':verify.sha(plan),
        'reproduction_files':verify.make_file_binding(tmp_path,[runtime,source]),
    }))
    revision.verify_saved_plan(tmp_path)
    source.write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA'):
        revision.verify_saved_plan(tmp_path)


def test_explicit_pair_labels_become_a_header_row(tmp_path):
    data=packet()
    sv=data['items'][0]['student_view']
    sv['conditions'][0]['content']='선지는 가 지역 / 나 지역에 지급할 총지원량(단위)을 나타낸다.'
    sv['choices']=['180 / 240','240 / 180','252 / 168','210 / 210','140 / 280']
    path=layout.build_hwpx(data,tmp_path/'headers.hwpx')
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('Contents/section0.xml'))
    table=root.find('.//hp:tbl[@rowCnt="6"][@colCnt="3"]',NS)
    assert table is not None
    text=''.join(t.text or '' for t in table.find('hp:tr',NS).findall('.//hp:t',NS))
    assert '가 지역' in text and '나 지역' in text


@pytest.mark.parametrize('split_number',[1,2])
def test_other_items_identical_fifth_choice_cannot_hide_a_split(tmp_path,split_number):
    data=packet();first=data['items'][0]
    first['student_view'].update(prompt='Choose.',conditions=[],choices=['A','B','C','D','E'])
    second=copy.deepcopy(first);second.update(number=2,item_id='FRG-SOC-TEST-Q02')
    data['items'].append(second)
    doc=fitz.open();page=doc.new_page(width=842,height=1189)
    page.insert_font(fontname='cjk',fontbuffer=fitz.Font('cjk').buffer)
    for item in data['items']:
        base=200+300*(item['number']-1)
        page.insert_text((90,base),f"{item['number']}. Choose. [1.5점]",fontname='cjk')
        for n,choice in enumerate(item['student_view']['choices']):
            x=470 if item['number']==split_number and n==4 else 90
            page.insert_text((x,base+30*(n+1)),layout.CIRCLED[n]+' '+choice,fontname='cjk')
    pdf=tmp_path/'split.pdf';doc.save(pdf);doc.close()
    hwpx=layout.build_hwpx(data,tmp_path/'split.hwpx')
    assert f'ITEM_SPLIT_ACROSS_COLUMNS: {split_number}' in verify.verify_exam(data,hwpx,pdf,{},tmp_path)['errors']
    with pytest.raises(ValueError,match='ITEM_SPLIT'):
        verify.item_geometry(data,pdf)


def test_reference_comparison_rejects_a_different_pdf(tmp_path):
    pdf=tmp_path/'exam.pdf';data=synthetic_pdf(pdf)
    reference={'pdf_sha256':'0'*64,'items':[{'number':1,'reference_number':1,'page':1,'bbox':[80,220,300,450]}]}
    with pytest.raises(ValueError,match='REFERENCE_PDF_SHA'):
        verify.build_item_review(data,pdf,tmp_path/'bad',reference_pdf=pdf,reference_map=reference)
    reference['pdf_sha256']=verify.sha(pdf)
    report=verify.build_item_review(data,pdf,tmp_path/'good',reference_pdf=pdf,reference_map=reference)
    assert (tmp_path/'good'/report['items'][0]['reference_image']).is_file()


def test_partial_replacement_of_a_repeated_source_line_is_rejected():
    source=request();entry=source['requests'][0]
    entry['source_content']='Repeated label\nOther\nRepeated label'
    entry['source_content_sha256']=hashlib.sha256(entry['source_content'].encode()).hexdigest()
    plan=visuals.make_visual_plan(source)
    plan['figures'][0].update(mode='schematic',replace=True,
                            lines=[{'text':'Repeated label','occurrence':1}])
    with pytest.raises(ValueError,match='PARTIAL_DUPLICATE_REPLACEMENT'):
        visuals.compile_visual_plan(source,plan)


def test_long_header_keeps_the_count_noun_with_its_subject(tmp_path):
    data=packet()
    data['items'][0]['student_view']['conditions'][0]['content']='국가 | 난민 아동 수 | 전체 취학 아동 수 | 취학 아동 중 난민 비율\nA | 12000명 | 30000명 | 30%'
    path=layout.build_hwpx(data,tmp_path/'table.hwpx')
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('Contents/section0.xml'))
    table=root.find('.//hp:tbl[@rowCnt="2"][@colCnt="4"]',NS)
    cell=table.find('hp:tr',NS).findall('hp:tc',NS)[2]
    text=''.join(t.text or '' for t in cell.findall('.//hp:t',NS))
    assert '아동 수' in text and '전체 취학\n아동 수'==text


def test_wide_header_is_not_given_an_unnecessary_extra_line(tmp_path):
    data=packet()
    data['items'][0]['student_view']['conditions'][0]['content']='보호안 | 보호하는 격자 묶음\n갑 | A·B·C'
    path=layout.build_hwpx(data,tmp_path/'wide.hwpx')
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('Contents/section0.xml'))
    table=root.find('.//hp:tbl[@rowCnt="2"][@colCnt="2"]',NS)
    cell=table.find('hp:tr',NS).findall('hp:tc',NS)[1]
    assert ''.join(t.text or '' for t in cell.findall('.//hp:t',NS))=='보호하는 격자 묶음'
