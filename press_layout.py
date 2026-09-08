"""Small social-exam compositor: native text/tables and bounded figure objects."""
from __future__ import annotations

import math
import re
from pathlib import Path
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
UNIT = 7200 / 25.4
FONT = '함초롬바탕'
BODY_SIZE = 12
DATA_SIZE = 11
COLUMN_MM = 112
CIRCLED = '①②③④⑤'


def parse_material(content: str) -> list[tuple[str, object]]:
    """Strip only Markdown table syntax; preserve prose/cells in source order."""
    blocks, rows = [], []
    def flush():
        if rows:
            if len({len(r) for r in rows}) != 1:
                raise ValueError('TABLE_COLUMN_MISMATCH')
            blocks.append(('table', list(rows)))
            rows.clear()
    for line in content.splitlines():
        if '|' in line:
            cells = [x.strip() for x in line.strip().strip('|').split('|')]
            if len(cells) > 1:
                if not all(re.fullmatch(r':?-{3,}:?', x) for x in cells):
                    rows.append(cells)
                continue
        flush()
        if line:
            blocks.append(('text', line))
    flush()
    return blocks


def student_units(item: dict) -> list[str]:
    """Text units for independent extraction comparison, including each table cell."""
    sv = item['student_view']
    units = [sv['prompt']]
    for condition in sv['conditions']:
        for kind, data in parse_material(condition['content']):
            if kind == 'text':
                units.append(data)
            else:
                units.extend(cell for row in data for cell in row)
    units.extend(sv['choices'])
    return units


def _formats(doc):
    char = {name: doc.ensure_run_style(font=FONT, size=size, bold=bold)
            for name, size, bold in [('body',BODY_SIZE,False),('data',DATA_SIZE,False),
                                    ('prompt',BODY_SIZE,True),('heading',24,True),('small',10,False)]}
    head = doc.headers[0]
    para = {}
    for name, spacing, after, keep, align in [
        ('body',135,60,True,'JUSTIFY'), ('last',135,450,False,'JUSTIFY'),
        ('prompt',135,260,True,'JUSTIFY'), ('data',135,100,True,'JUSTIFY'),
        ('cell',135,0,False,'LEFT'), ('title',140,600,True,'CENTER'),
        ('spacer',100,0,False,'LEFT')]:
        para[name] = head.ensure_paragraph_format(
            alignment=align, line_spacing_percent=spacing,
            margins={'prev':0, 'next':after,'left':0,'right':0,'intent':0},
            break_setting={'keep_with_next':keep,'keep_lines':True,'widow_orphan':True})
    return char, para


def _table(doc, rows, char, para):
    cols = len(rows[0])
    width = round(COLUMN_MM * UNIT)
    weights = [max(3, min(28, max(len(row[c]) for row in rows))) for c in range(cols)]
    # Square-root compression balances long narrative columns and short numeric ones.
    weights = [math.sqrt(x) for x in weights]
    widths = [width*w/sum(weights) for w in weights]
    heights = [max(2300, max(math.ceil(max(1,len(row[c]))/(widths[c]/(DATA_SIZE*100)))
                 for c in range(cols))*DATA_SIZE*145 + 500) for row in rows]
    border = doc.headers[0].ensure_basic_border_fill()
    border_id = border if isinstance(border,str) else border.get('id')
    table = doc.add_table(len(rows),cols,width=width,height=int(sum(heights)),
                          border_fill_id_ref=border_id,para_pr_id_ref=para['data'],
                          char_pr_id_ref=char['data'])
    table.set_column_widths(weights)
    table.element.set('pageBreak','NONE')
    for ri,row in enumerate(rows):
        for ci,value in enumerate(row):
            cell=table.cell(ri,ci)
            cell.set_text(value)
            cell.set_size(height=int(heights[ri]))
            sub=cell.element.find(HP+'subList')
            if sub is not None:
                sub.set('vertAlign','CENTER')
            margin=cell.element.find(HP+'cellMargin')
            if margin is not None:
                for side in ('left','right','top','bottom'):
                    margin.set(side,'200')
            for p in cell.paragraphs:
                p.element.set('paraPrIDRef',para['cell'])
                for r in p.element.findall(HP+'run'):
                    r.set('charPrIDRef',char['data'])
    return table


def build_hwpx(packet: dict, output: Path, item_numbers=None, *, visuals=None,
               artifact_root=None, column_starts=(), teacher=False) -> Path:
    items=[i for i in packet['items'] if item_numbers is None or i['number'] in item_numbers]
    if visuals:
        from press_verify import validate_visual_result
        validate_visual_result(packet['visual_handoff'],visuals,artifact_root)
        visuals=visuals['display']
    for i in items:
        if len(i['student_view']['choices']) != 5:
            raise ValueError('CHOICES_REQUIRE_FIVE')
    doc=HwpxDocument.new()
    doc.set_page_setup(width_mm=297,height_mm=420,orientation='PORTRAIT',
        margin_left_mm=31,margin_right_mm=31,margin_top_mm=38,margin_bottom_mm=27,
        header_margin_mm=12,footer_margin_mm=13)
    # Measured from this Hancom version's own portrait blank and supplied template.
    # Its saved portrait is WIDELY with width < height; PORTRAIT rotates on open.
    doc.sections[0].properties.set_page_size(orientation='WIDELY')
    chars,paras=_formats(doc)
    header=doc.set_header_text('2028 통합사회   |   '+('정답·해설' if teacher else '연습 문제')+'   ·   편집 검토 초안')
    doc.set_page_number(target='footer',prefix='',suffix='',align='CENTER')
    doc.add_paragraph('2028 통합사회 '+('정답·해설' if teacher else '연습 문제'),
        para_pr_id_ref=paras['title'],char_pr_id_ref=chars['heading'])
    doc.add_paragraph(f"{packet['campaign_id']}   |   {len(items)}문항 · {sum(i['points'] for i in items):g}점   |   편집 검토 초안",
        para_pr_id_ref=paras['title'],char_pr_id_ref=chars['small'])
    if not teacher:
        doc.add_paragraph('성명 ____________________     수험 번호 ____________________',
            para_pr_id_ref=paras['title'],char_pr_id_ref=chars['data'])
    start=doc.add_paragraph('',para_pr_id_ref=paras['spacer'],char_pr_id_ref=chars['small'])
    doc.set_columns(2,col_type='NEWSPAPER',same_gap=round(11*UNIT),
                    separator_type='SOLID',separator_width='0.12 mm',separator_color='#000000',paragraph=start)
    for idx,item in enumerate(items):
        if idx and item['number'] in column_starts:
            doc.add_paragraph('',columnBreak='1',para_pr_id_ref=paras['spacer'],char_pr_id_ref=chars['small'])
        sv=item['student_view']
        if teacher:
            t=item['teacher']
            doc.add_paragraph(f"{item['number']}. 정답 {CIRCLED[t['answer']-1]}  [{item['points']:g}점]",
                para_pr_id_ref=paras['prompt'],char_pr_id_ref=chars['prompt'])
            doc.add_paragraph(t['rationale'],para_pr_id_ref=paras['data'],char_pr_id_ref=chars['body'])
            for step in t.get('solution_steps',[]):
                doc.add_paragraph(f"풀이 {step['step']}. {step['operation']}",para_pr_id_ref=paras['data'],char_pr_id_ref=chars['data'])
            for ev in t.get('choice_evaluations',[]):
                if ev.get('refutation'):
                    doc.add_paragraph(f"{CIRCLED[ev['choice']-1]} {ev['refutation']}",para_pr_id_ref=paras['data'],char_pr_id_ref=chars['data'])
            doc.add_paragraph('',para_pr_id_ref=paras['last'],char_pr_id_ref=chars['small'])
            continue
        doc.add_paragraph(f"{item['number']}. {sv['prompt']} [{item['points']:g}점]",
            para_pr_id_ref=paras['prompt'],char_pr_id_ref=chars['prompt'])
        for condition in sv['conditions']:
            key=item['item_id']+'|'+condition['condition_id']
            graphic=(visuals or {}).get(key,{})
            replacement=graphic.get('replace_lines',[])
            source_lines=condition['content'].splitlines()
            if any(line not in source_lines for line in replacement):
                raise ValueError('VISUAL_REPLACEMENT_NOT_IN_SOURCE')
            emitted=False
            pending=[]
            def write_pending():
                for kind,data in parse_material('\n'.join(pending)):
                    if kind=='table':
                        _table(doc,data,chars,paras)
                    else:
                        doc.add_paragraph(data,para_pr_id_ref=paras['data'],char_pr_id_ref=chars['data'])
                pending.clear()
            for line in source_lines:
                if line in replacement:
                    if not emitted:
                        write_pending()
                        path=Path(artifact_root)/graphic['png_path']
                        width=min(COLUMN_MM,float(graphic['width_mm']))
                        height=float(graphic['height_mm'])*width/float(graphic['width_mm'])
                        doc.add_picture(path.read_bytes(),'png',width_mm=width,height_mm=height,
                            para_pr_id_ref=paras['data'],char_pr_id_ref=chars['data'])
                        emitted=True
                else:
                    pending.append(line)
            write_pending()
        for n,choice in enumerate(sv['choices']):
            doc.add_paragraph(CIRCLED[n]+' '+choice,
                para_pr_id_ref=paras['last' if n==4 else 'body'],char_pr_id_ref=chars['body'])
    # All body geometry is recalculated by Hangul; stale library line caches are removed.
    for section in doc.sections:
        # python-hwpx also keeps header/footer definitions under secPr, unlike
        # Hancom's native saved file. Keep only the actual paragraph controls.
        for child in list(section.properties.element):
            if child.tag in {HP+'header',HP+'footer',HP+'headerApply',HP+'footerApply'}:
                section.properties.element.remove(child)
        section.remove_layout_caches()
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    doc.save_to_path(str(output))
    report=validate_editor_open_safety(output)
    if not report.ok:
        raise ValueError('HWPX_PACKAGE_INVALID: '+report.summary)
    return output


def render_hangul(hwpx: Path, pdf: Path) -> dict:
    """Reopen the generated HWPX in a private Hancom instance; PDF comes from it."""
    import win32com.client
    import fitz
    app=win32com.client.DispatchEx('HWPFrame.HwpObject')
    try:
        if not app.RegisterModule('FilePathCheckDLL','FilePathCheckerModule'):
            raise RuntimeError('HANGUL_PATH_MODULE_UNAVAILABLE')
        if not app.Open(str(Path(hwpx).resolve()),'HWPX','forceopen:true'):
            raise RuntimeError('HANGUL_OPEN_FAILED')
        pages=int(app.PageCount)
        version=app.Version
        if not app.SaveAs(str(Path(pdf).resolve()),'PDF',''):
            raise RuntimeError('HANGUL_PDF_FAILED')
    finally:
        app.Quit()
    with fitz.open(pdf) as rendered:
        if len(rendered)!=pages or pages<1:
            raise RuntimeError('HANGUL_PDF_PAGE_MISMATCH')
    return {'engine':'Hancom HWP COM','version':version,'opened':True,'pages':pages}
