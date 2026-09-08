"""Small social-exam compositor: native text/tables and bounded figure objects."""
from __future__ import annotations

import math
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from hwpx.document import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
UNIT = 7200 / 25.4
FONT = '함초롬바탕'
BODY_SIZE = 11.5
DATA_SIZE = 11
COLUMN_MM = 112
MATERIAL_MM = 109
INNER_MM = 105.8
CIRCLED = '①②③④⑤'
# Item-specific grouping from the source/reference comparison. Dialogue versus
# independent case/rule stays in separate cards; related data/notes share a card.
UNIFIED_MATERIAL = {
    'M01': {2,3,4,5,8,9,11,12,14,15,18,19,20,21,22,25},
    'M02': {2,6,7,8,9,10,11,12,17,18,19,20,21,23,24,25},
    'M03': {3,5,6,9,12,13,19,21,22,23,24,25},
}


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
                                    ('prompt',BODY_SIZE,False),('number',13.8,True),
                                    ('heading',26,True),('small',10,False),('note',10,False)]}
    head = doc.headers[0]
    para = {}
    for name, spacing, after, keep, align in [
        ('body',125,30,True,'JUSTIFY'), ('last',125,900,False,'JUSTIFY'),
        ('prompt',130,400,True,'JUSTIFY'), ('data',125,170,True,'JUSTIFY'),
        ('note',120,130,True,'LEFT'), ('dialogue',125,150,True,'JUSTIFY'),
        ('frame',100,450,True,'LEFT'),
        ('cell',120,0,False,'CENTER'), ('cell_text',120,0,False,'LEFT'),
        ('title',130,450,True,'CENTER'),
        ('spacer',100,0,False,'LEFT')]:
        left,indent = (1000,-1000) if name in ('body','last','prompt') else (0,0)
        if name=='frame': left=round(3*UNIT)
        if name=='dialogue': left,indent=1700,-1700
        para[name] = head.ensure_paragraph_format(
            alignment=align, line_spacing_percent=spacing,
            margins={'prev':0, 'next':after,'left':left,'right':0,'intent':indent},
            break_setting={'keep_with_next':keep,'keep_lines':True,'widow_orphan':True})
    return char, para


def _table(doc, rows, char, para, width_mm=INNER_MM, header=True):
    cols = len(rows[0])
    width = round(width_mm * UNIT)
    weights = [max(3, min(28, max(len(row[c]) for row in rows))) for c in range(cols)]
    # Square-root compression balances long narrative columns and short numeric ones.
    weights = [math.sqrt(x) for x in weights]
    widths = [width*w/sum(weights) for w in weights]
    # Hangul expands rows to content. A small minimum prevents the former
    # length-based estimate from allocating several blank lines per table row.
    heights = [1700 for _ in rows]
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
            cell.element.set('hasMargin','1')
            # Keep a long unit together on its own header line where the source provides one.
            shown=value
            if header and ri==0 and len(value)>=10:
                shown=re.sub(r'\s*(\([^()]+\))$',r'\n\1',value)
                spaces=[i for i,c in enumerate(value) if c==' ']
                estimated=sum(2 if unicodedata.east_asian_width(c) in 'WFA' else 1 for c in value)*DATA_SIZE/2
                if shown==value and spaces and len(value)<=18 and estimated>widths[ci]/100-4.6:
                    split=min(spaces,key=lambda i:abs(i-len(value)/2))
                    shown=value[:split]+'\n'+value[split+1:]
            cell.set_text(shown)
            cell.set_size(height=int(heights[ri]))
            sub=cell.element.find(HP+'subList')
            if sub is not None:
                sub.set('vertAlign','CENTER')
            margin=cell.element.find(HP+'cellMargin')
            if margin is not None:
                for side in ('left','right','top','bottom'):
                    margin.set(side,'230' if side in ('left','right') else '150')
            for p in cell.paragraphs:
                p.element.set('paraPrIDRef',para['cell_text' if ri and len(value)>18 else 'cell'])
                for r in p.element.findall(HP+'run'):
                    r.set('charPrIDRef',char['data'])
    return table


def _material_frame(doc, paragraphs, chars, paras):
    """Group source material in an editable native cell, retaining object order."""
    border=doc.headers[0].ensure_basic_border_fill()
    table=doc.add_table(1,1,width=round(MATERIAL_MM*UNIT),height=1600,
        border_fill_id_ref=border,para_pr_id_ref=paras['frame'],char_pr_id_ref=chars['data'])
    table.element.set('pageBreak','NONE')
    cell=table.cell(0,0)
    cell.element.set('hasMargin','1')
    sub=cell.element.find(HP+'subList')
    sub.set('vertAlign','TOP')
    for child in list(sub): sub.remove(child)
    for p in paragraphs:
        doc.sections[0].element.remove(p)
        sub.append(p)
    margin=cell.element.find(HP+'cellMargin')
    for side in ('left','right','top','bottom'): margin.set(side,'450')
    return table


def _paired_choices(doc, choices, chars, paras, conditions=()):
    parts=[re.fullmatch(r'(.+?)\s+(—|/)\s+(.+)',c) for c in choices]
    if not all(parts) or max(map(len,choices))>30:
        return False
    rows=[[CIRCLED[n]+' '+m[1],m[2],m[3]] for n,m in enumerate(parts)]
    headers=[]
    for condition in conditions:
        match=re.search(r'선지는 (.+?) / (.+?)에 지급할 총지원량\(단위\)을 나타낸다\.',condition['content'])
        if match: headers=[match[1],'',match[2]];break
    if headers: rows.insert(0,headers)
    table=_table(doc,rows,chars,paras,width_mm=76,header=bool(headers))
    table.set_column_widths([45,10,45])
    table.paragraph.element.set('paraPrIDRef',paras['last'])
    _borderless(doc, table)
    for n in range(len(rows)):
        for c in range(3):
            for p in table.cell(n,c).paragraphs:
                p.element.set('paraPrIDRef',paras['cell_text' if c==0 and not(headers and n==0) else 'cell'])
    return True


def _borderless(doc, table):
    fills=doc.headers[0].element.find('.//'+HH+'borderFills')
    source=next(b for b in fills if b.get('id')==table.element.get('borderFillIDRef'))
    blank=deepcopy(source)
    identifier=str(max(int(b.get('id')) for b in fills)+1)
    blank.set('id',identifier)
    for edge in blank:
        if edge.tag.endswith('Border'): edge.set('type','NONE')
    fills.append(blank);fills.set('itemCnt',str(len(fills)))
    table.element.set('borderFillIDRef',identifier)
    for cell in table.element.findall('.//'+HP+'tc'):
        cell.set('borderFillIDRef',identifier)


def _compact_choices(doc, choices, chars, paras):
    labels=[m+' '+c for m,c in zip(CIRCLED,choices,strict=True)]
    # Conservative width estimate, followed by inspection of the actual Hancom PDF.
    widths=[sum(2 if unicodedata.east_asian_width(c) in 'WFA' else 1 for c in s)
            * BODY_SIZE / 2 + 8 for s in labels]
    if any('\n' in c for c in choices) or sum(widths)>COLUMN_MM*72/25.4:
        return False
    table=_table(doc,[labels],chars,paras,width_mm=COLUMN_MM,header=False)
    table.set_column_widths(widths)
    table.paragraph.element.set('paraPrIDRef',paras['last'])
    _borderless(doc,table)
    for cell in table.element.findall('.//'+HP+'tc'):
        for run in cell.findall('.//'+HP+'run'):
            run.set('charPrIDRef',chars['body'])
    return True


def _page_rules(doc, header):
    """Native header drawings repeat the page frame even beside a short column."""
    run=header.element.find('.//'+HP+'run')
    # Header shapes use the header paragraph origin in this Hancom renderer.
    # These offsets align with the native 235 mm text area and lower folio.
    for x,y,dx,dy in [(0,7.4,235,0),(117.5,45.3,0,298.5)]:
        line=doc.add_line(end_x=round(dx*UNIT),end_y=round(dy*UNIT),
                          line_width='40',treat_as_char=False)
        element=line.element
        # Native Hangul lines use a nonzero 100x100 local coordinate space;
        # a zero-width/height orgSz from python-hwpx is discarded on open.
        element.find(HP+'orgSz').set('width','100')
        element.find(HP+'orgSz').set('height','100')
        core='{http://www.hancom.co.kr/hwpml/2011/core}'
        element.find(core+'endPt').set('x','100')
        element.find(core+'endPt').set('y','100')
        scale=element.find('.//'+core+'scaMatrix')
        scale.set('e1',str(round(dx*UNIT)/100));scale.set('e5',str(round(dy*UNIT)/100))
        element.find(HP+'sz').set('width',str(max(1,round(dx*UNIT))))
        element.find(HP+'sz').set('height',str(max(1,round(dy*UNIT))))
        pos=element.find(HP+'pos')
        pos.set('horzRelTo','PARA');pos.set('vertRelTo','PARA')
        pos.set('horzOffset',str(round(x*UNIT)));pos.set('vertOffset',str(round(y*UNIT)))
        element.set('textWrap','IN_FRONT_OF_TEXT');element.set('textFlow','BOTH_SIDES')
        run.append(element)
        doc.sections[0].element.remove(line.paragraph.element)


def _first_page_rule(doc, identity_paragraph, header):
    # Reuse the normalized horizontal native shape, anchored only to page 1's
    # full-width identity line. This sits below the name fields, above the stems.
    source=header.element.find('.//'+HP+'line')
    rule=deepcopy(source)
    identifier=str(int(rule.get('id'))+100)
    rule.set('id',identifier);rule.set('instid',identifier)
    rule.find(HP+'pos').set('vertOffset',str(round(6.4*UNIT)))
    identity_paragraph.element.find(HP+'run').append(rule)


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
    for p in header.element.findall('.//'+HP+'p'):
        p.set('paraPrIDRef',paras['title'])
        for run in p.findall(HP+'run'): run.set('charPrIDRef',chars['small'])
    if not teacher: _page_rules(doc,header)
    doc.set_page_number(target='footer',prefix='',suffix='',align='CENTER')
    doc.add_paragraph('2028 통합사회 '+('정답·해설' if teacher else '연습 문제'),
        para_pr_id_ref=paras['title'],char_pr_id_ref=chars['heading'])
    edition=re.sub(r'FRG-SOC-2028-M0([12])',r'제\1회',packet.get('edition_label',packet['campaign_id']))
    doc.add_paragraph(f"{edition}   |   {len(items)}문항 · {sum(i['points'] for i in items):g}점   |   편집 검토 초안",
        para_pr_id_ref=paras['title'],char_pr_id_ref=chars['small'])
    if teacher and any('editorial_solution' in i for i in items):
        solution_label=doc.ensure_run_style(font=FONT,size=BODY_SIZE,bold=True)
        for offset in range(0,len(items),10):
            key='    '.join(f"{i['number']:02d}. {CIRCLED[i['teacher']['answer']-1]}" for i in items[offset:offset+10])
            doc.add_paragraph(key,para_pr_id_ref=paras['title'],char_pr_id_ref=chars['small'])
    if not teacher:
        identity=doc.add_paragraph('성명 ____________________     수험 번호 ____________________',
            para_pr_id_ref=paras['title'],char_pr_id_ref=chars['data'])
        _first_page_rule(doc,identity,header)
    start=doc.add_paragraph('',para_pr_id_ref=paras['spacer'],char_pr_id_ref=chars['small'])
    col_type='BALANCED_NEWSPAPER' if teacher and any('editorial_solution' in i for i in items) else 'NEWSPAPER'
    doc.set_columns(2,col_type=col_type,same_gap=round(11*UNIT),
                    separator_type='SOLID',separator_width='0.12 mm',separator_color='#000000',paragraph=start)
    for idx,item in enumerate(items):
        if idx and item['number'] in column_starts:
            doc.add_paragraph('',columnBreak='1',para_pr_id_ref=paras['spacer'],char_pr_id_ref=chars['small'])
        sv=item['student_view']
        if teacher:
            t=item['teacher']
            if 'editorial_solution' in item:
                e=item['editorial_solution']
                doc.add_paragraph(f"{item['number']}. {e['topic']}   정답 {CIRCLED[t['answer']-1]}",
                    para_pr_id_ref=paras['prompt'],char_pr_id_ref=solution_label)
                for n,text in enumerate(e['explanation']):
                    p=doc.add_paragraph('',para_pr_id_ref=paras['data'],char_pr_id_ref=chars['body'])
                    if n==0: p.add_run('정답 해설  ',char_pr_id_ref=solution_label)
                    p.add_run(text,char_pr_id_ref=chars['body'])
                doc.add_paragraph('[오답피하기]',para_pr_id_ref=paras['data'],char_pr_id_ref=solution_label)
                for w in e['wrong_answers']:
                    doc.add_paragraph(f"{CIRCLED[w['choice']-1]} {w['text']}",
                        para_pr_id_ref=paras['data'],char_pr_id_ref=chars['body'])
                doc.add_paragraph('',para_pr_id_ref=paras['last'],char_pr_id_ref=chars['small'])
                continue
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
        prompt=doc.add_paragraph(f"{item['number']}. ",
            para_pr_id_ref=paras['prompt'],char_pr_id_ref=chars['number'])
        prompt.add_run(f"{sv['prompt']} [{item['points']:g}점]",char_pr_id_ref=chars['prompt'])
        section=doc.sections[0].element
        combined_start=len(section)
        unified=item['number'] in UNIFIED_MATERIAL.get(packet['campaign_id'][-3:],set())
        for condition in sv['conditions']:
            section=doc.sections[0].element
            first_material=len(section)
            key=item['item_id']+'|'+condition['condition_id']
            graphic=(visuals or {}).get(key,{})
            replacement=graphic.get('replace_lines',[])
            insert_before=graphic.get('insert_before_line')
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
                        role='note' if data.startswith(('*','출처:','단위:')) else 'dialogue' if re.match(r'^(갑|을|병|정|학생|교사|주민)\s*:',data) else 'data'
                        doc.add_paragraph(data,para_pr_id_ref=paras[role],char_pr_id_ref=chars['note' if role=='note' else 'data'])
                pending.clear()
            def write_picture():
                path=Path(artifact_root)/graphic['png_path']
                width=min(INNER_MM,float(graphic['width_mm']))
                height=float(graphic['height_mm'])*width/float(graphic['width_mm'])
                doc.add_picture(path.read_bytes(),'png',width_mm=width,height_mm=height,
                    para_pr_id_ref=paras['data'],char_pr_id_ref=chars['data'])
            for line in source_lines:
                if line==insert_before and not emitted:
                    write_pending()
                    write_picture()
                    emitted=True
                if line in replacement:
                    if not emitted:
                        write_pending()
                        write_picture()
                        emitted=True
                else:
                    pending.append(line)
            write_pending()
            if not unified:
                _material_frame(doc,list(section)[first_material:],chars,paras)
        if unified:
            _material_frame(doc,list(section)[combined_start:],chars,paras)
        if (_paired_choices(doc,sv['choices'],chars,paras,sv['conditions'])
            or _compact_choices(doc,sv['choices'],chars,paras)):
            continue
        for n,choice in enumerate(sv['choices']):
            doc.add_paragraph(CIRCLED[n]+' '+choice,
                para_pr_id_ref=paras['last' if n==4 else 'body'],char_pr_id_ref=chars['body'])
    # All body geometry is recalculated by Hangul; stale library line caches are removed.
    for section in doc.sections:
        # python-hwpx also keeps header/footer definitions under secPr, unlike
        # Hancom's native saved file. Keep only the actual paragraph controls.
        for child in list(section.properties.element):
            if child.tag in {HP+'header',HP+'footer',HP+'headerApply',HP+'footerApply'}:
                if child.tag in {HP+'header',HP+'footer'}:
                    # python-hwpx makes a separate native control when the story
                    # is created; later style/drawing changes update the story only.
                    for control in section.element.findall('.//'+HP+'ctrl'):
                        for old in list(control):
                            if old.tag==child.tag and old.get('id')==child.get('id'):
                                control.replace(old,deepcopy(child))
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
