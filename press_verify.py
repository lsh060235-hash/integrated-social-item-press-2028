"""Mechanical verification is evidence, never a human publication approval."""
from __future__ import annotations
import hashlib
import html
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import fitz
from PIL import Image, ImageDraw, ImageChops, ImageStat
from press_layout import parse_material, student_units, CIRCLED


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def normalized(text):
    return re.sub(r'[\s\u200b\ufeff]+','',text)


def missing_units(units,text):
    actual=normalized(text)
    return [u for u in units if normalized(u) not in actual]


def item_frame(item,text,next_item=None):
    actual=normalized(text)
    def stem(i):
        return normalized(f"{i['number']}. {i['student_view']['prompt']} [{i['points']:g}점]")
    target=stem(item)
    if actual.count(target)!=1: raise ValueError('STEM_POINTS_MISSING_OR_DUPLICATED')
    start=actual.index(target)
    end=actual.find(stem(next_item),start+len(target)) if next_item else len(actual)
    if end<0: raise ValueError('NEXT_ITEM_STEM_POINTS_MISSING')
    frame=actual[start:end]
    cursor=len(target)
    for marker,choice in zip(CIRCLED,item['student_view']['choices'],strict=True):
        expected=normalized(marker+' '+choice)
        pos=frame.find(expected,cursor)
        if pos<0: raise ValueError('CHOICE_ORDER_OR_MARKER_MISMATCH')
        cursor=pos+len(expected)
    return frame


def match_pdf_figure(doc,path):
    """Match displayed PDF raster pixels, allowing only native JPEG quantization."""
    with Image.open(path) as opened:
        expected=opened.convert('L'); size=expected.size
        small=expected.resize((256,128))
    found=[]
    for pn,page in enumerate(doc,1):
        for info in page.get_image_info(xrefs=True):
            if (info['width'],info['height'])!=size or not info['xref']:
                continue
            data=doc.extract_image(info['xref'])
            with Image.open(io.BytesIO(data['image'])) as opened:
                actual=opened.convert('L').resize((256,128))
            delta=ImageStat.Stat(ImageChops.difference(small,actual)).mean[0]
            if delta<=2.0:
                x0,y0,x1,y1=info['bbox']
                if x0<0 or y0<0 or x1>page.rect.width or y1>page.rect.height: continue
                found.append({'page':pn,'column':1+int(x0>page.rect.width/2-8),'pixel_mean_error':round(delta,4)})
    return found


def validate_visual_result(request,result,root):
    from integrated_social_forge.visual_handoff import validate_visual_artifacts
    report=validate_visual_artifacts(request,result['receipt'],result['artifacts'],Path(root))
    expected={a['item_id']+'|'+a['data_id']:a for a in result['artifacts']}
    requests={a['item_id']+'|'+a['data_id']:a for a in request['requests']}
    if set(result['display'])!=set(expected): raise ValueError('DISPLAY_COVERAGE')
    for key,g in result['display'].items():
        a=expected[key]
        if g['png_path']!=a['rendered_asset_path']:
            raise ValueError('DISPLAY_PAIR_MISMATCH: '+key)
        spec=json.loads((Path(root)/a['figure_spec_path']).read_text(encoding='utf-8'))
        if spec['source_content']!=requests[key]['source_content']:
            raise ValueError('DISPLAY_SOURCE_MISMATCH: '+key)
        if g['replace_lines'] and g['replace_lines']!=spec['core_variables']['lines']:
            raise ValueError('DISPLAY_REPLACEMENT_MISMATCH: '+key)
        marker=g.get('insert_before_line')
        if marker is not None or spec.get('insert_before_line') is not None:
            if (marker!=spec.get('insert_before_line') or marker not in spec['source_content'].splitlines()
                or g['replace_lines']):
                raise ValueError('DISPLAY_INSERTION_MISMATCH: '+key)
        if any(g[k]!=spec[k] for k in ('width_mm','height_mm')):
            raise ValueError('DISPLAY_SIZE_MISMATCH: '+key)
    return report


def make_manifest(root:Path,binding:dict) -> dict:
    return {'schema_version':'integrated-social-press-return-v0.1',
        'status':'DRAFT_FOR_HUMAN_REVIEW','human_release_approval':None,'input_binding':binding,
        'files':[{'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
                 for p in sorted(root.rglob('*')) if p.is_file() and p.name!='return-manifest.json']}


def verify_manifest(root,manifest):
    root=Path(root).resolve()
    for f in manifest['files']:
        rel=f['path']
        if any(c in rel for c in ('\\',':','\x00')) or any(p in ('','..','.') for p in rel.split('/')):
            raise ValueError('UNSAFE_RETURN_PATH')
        p=(root/rel).resolve()
        if not p.is_relative_to(root):
            raise ValueError('UNSAFE_RETURN_PATH')
        if not p.is_file():
            raise ValueError('RETURN_FILE_MISSING: '+rel)
        if sha(p)!=f['sha256']:
            raise ValueError('RETURN_SHA_MISMATCH: '+rel)


def preview_pdf(pdf:Path,out:Path) -> dict:
    out.mkdir(parents=True,exist_ok=True)
    thumbs=[]
    with fitz.open(pdf) as doc:
        for i,page in enumerate(doc):
            name=f'page-{i+1:02d}.png'
            page.get_pixmap(matrix=fitz.Matrix(1.35,1.35),alpha=False).save(out/name)
            im=Image.open(out/name).convert('RGB'); im.thumbnail((300,425))
            tile=Image.new('RGB',(320,457),'#eeeeee'); tile.paste(im,((320-im.width)//2,8))
            ImageDraw.Draw(tile).text((12,436),f'PAGE {i+1}',fill='black')
            thumbs.append(tile)
    sheet=Image.new('RGB',(320*3,457*((len(thumbs)+2)//3)),'white')
    for i,t in enumerate(thumbs): sheet.paste(t,((i%3)*320,(i//3)*457))
    sheet.save(out/'all-pages.png')
    return {'page_count':len(thumbs),'contact_sheet':(out/'all-pages.png').as_posix()}


def has_page_frame(page):
    rects=[drawing['rect'] for drawing in page.get_drawings()]
    horizontal=any(r.width>600 and r.height<2 and 90<r.y0<150 for r in rects)
    vertical=any(r.height>800 and r.width<2 and abs(r.x0-page.rect.width/2)<25
                 and r.y0<250 and 1050<r.y1<1085 for r in rects)
    return horizontal and vertical


def item_geometry(packet, pdf):
    """Locate each complete item in rendered column text; retain glyph coordinates."""
    columns=[]
    with fitz.open(pdf) as doc:
        for pn,page in enumerate(doc,1):
            groups=[[],[]]
            for block in page.get_text('rawdict')['blocks']:
                for line in block.get('lines',[]):
                    chars=[c for span in line['spans'] for c in span['chars'] if normalized(c['c'])]
                    x,y,_,_=line['bbox']
                    groups[int(x>page.rect.width/2-8)].append((y,x,chars))
            for col,lines in enumerate(groups,1):
                chars=[c for _,_,row in sorted(lines,key=lambda t:(t[0],t[1])) for c in row]
                columns.append((pn,col,''.join(normalized(c['c']) for c in chars),chars))
        found=[]
        for ix,item in enumerate(packet['items']):
            stem=normalized(f"{item['number']}. {item['student_view']['prompt']} [{item['points']:g}점]")
            last=normalized(CIRCLED[4]+item['student_view']['choices'][4])
            starts=[(pn,col,text,chars,text.index(stem)) for pn,col,text,chars in columns if stem in text]
            if len(starts)!=1: raise ValueError('ITEM_REVIEW_STEM_LOCATION: '+str(item['number']))
            pn,col,text,chars,start=starts[0]
            end=text.find(last,start+len(stem))
            next_start=len(text)
            if ix+1<len(packet['items']):
                following=packet['items'][ix+1]
                next_stem=normalized(f"{following['number']}. {following['student_view']['prompt']} [{following['points']:g}점]")
                position=text.find(next_stem,start+len(stem))
                if position>=0: next_start=position
            if end<0 or end>=next_start: raise ValueError('ITEM_SPLIT_ACROSS_COLUMNS: '+str(item['number']))
            rect=fitz.Rect(chars[start]['bbox'])
            for c in chars[start:end+len(last)]: rect.include_rect(c['bbox'])
            page=doc[pn-1]
            for image in page.get_image_info():
                box=fitz.Rect(image['bbox'])
                if (1+int(box.x0>page.rect.width/2-8)==col and rect.y0<=box.y0<rect.y1):
                    rect.include_rect(box)
            found.append({'number':item['number'],'page':pn,'column':col,
                          'bbox':list(rect),'height_pt':round(rect.height,2)})
    return found


def build_item_review(packet, pdf, out, *, reference_pdf=None, reference_map=None):
    """Produce unapproved, PDF-bound question crops and a readable review checklist."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    items=item_geometry(packet,pdf)
    if reference_pdf is not None:
        if not reference_map or reference_map.get('pdf_sha256')!=sha(reference_pdf):
            raise ValueError('REFERENCE_PDF_SHA_MISMATCH')
        refs=reference_map.get('items',[])
        if sorted(r['number'] for r in refs)!=sorted(i['number'] for i in items):
            raise ValueError('REFERENCE_ITEM_COVERAGE')
        by_number={r['number']:r for r in refs}
        with fitz.open(reference_pdf) as doc:
            for item in items:
                ref=by_number[item['number']]
                if type(ref['page']) is not int or not 1<=ref['page']<=len(doc):
                    raise ValueError('REFERENCE_PAGE_INVALID')
                page=doc[ref['page']-1];box=fitz.Rect(ref['bbox'])
                if box.is_empty or box.is_infinite or not page.rect.contains(box):
                    raise ValueError('REFERENCE_CROP_INVALID')
                name=f"reference-{item['number']:02d}.png"
                page.get_pixmap(matrix=fitz.Matrix(2,2),clip=box,alpha=False).save(out/name)
                item.update(reference_image=name,reference_number=ref['reference_number'],
                            reference_page=ref['page'],reference_bbox=list(box))
    with fitz.open(pdf) as doc:
        for item in items:
            page=doc[item['page']-1]
            bbox=fitz.Rect(item['bbox'])
            middle=page.rect.width/2-8
            clip=fitz.Rect(70 if item['column']==1 else middle,
                           max(0,bbox.y0-8),middle if item['column']==1 else page.rect.width-65,
                           min(page.rect.height,bbox.y1+8))
            name=f"Q{item['number']:02d}.png"
            page.get_pixmap(matrix=fitz.Matrix(2,2),clip=clip,alpha=False).save(out/name)
            item.update(image=name,status='PENDING',crop_bbox=list(clip))
    report={'schema_version':'press-item-review-v1','pdf_sha256':sha(pdf),'items':items,
            'checks':['자료 유형과 비교 기출의 형식','표 제목·단위·줄바꿈','도식 수치·범례',
                      '선택지 배열·읽기 순서','잘림·겹침·문항 간 여백'],
            'human_release_approval':None}
    if reference_pdf is not None: report['reference']=reference_map
    (out/'items.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cards=[]
    for i in items:
        ref=(f'<section><h3>형식 참조 {html.escape(str(i["reference_number"]))}번</h3>'
             f'<img src="{i["reference_image"]}" alt="공식 예시문항 형식 참조"></section>') if 'reference_image' in i else ''
        cards.append(f'<article><h2>{i["number"]}번 · {i["page"]}쪽 {i["column"]}단</h2>'
            f'<p>검토 대기 · 문항 높이 {i["height_pt"]} pt</p><div class="compare">'+ref+
            f'<section><h3>Press 수정본</h3><img src="{i["image"]}" alt="{i["number"]}번 전체 문항"></section></div></article>')
    checks=' / '.join(report['checks'])
    (out/'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<title>문항별 지면 검토</title><style>body{max-width:1100px;margin:32px auto;font-family:sans-serif;'
        'background:#eee}article{background:white;padding:24px;margin:24px 0}img{max-width:100%;'
        'width:670px}.compare{display:flex;gap:20px}.compare section{flex:1;min-width:0}p{line-height:1.6}'
        '@media(max-width:700px){.compare{display:block}}</style><h1>문항별 지면 검토</h1><p>'+html.escape(checks)+
        '</p><p>자동 생성된 검토 자료입니다. 문항별 형식 검토와 최종 출고 승인은 별도입니다.</p>'+''.join(cards)+'</html>',encoding='utf-8')
    return report


def balance_last_column(locations):
    """Move the last of exactly two final-page items only when both occupy the left."""
    if not locations: return ()
    last=[i for i in locations if i['page']==locations[-1]['page']]
    if len(last)==2 and all(i['column']==1 and i['whole_item_same_column'] for i in last):
        return (last[-1]['number'],)
    return ()


def validate_item_review(packet,pdf,review):
    if review.get('exam_pdf_sha256')!=sha(pdf):
        raise ValueError('STALE_ITEM_REVIEW')
    if review.get('item_numbers_reviewed')!=[i['number'] for i in packet['items']]:
        raise ValueError('INCOMPLETE_ITEM_REVIEW')


def verify_exam(packet,hwpx,pdf,visual_result,artifact_root,item_numbers=None):
    items=[i for i in packet['items'] if item_numbers is None or i['number'] in item_numbers]
    display=visual_result.get('display',{})
    errors=[]
    with zipfile.ZipFile(hwpx) as z:
        roots=[ET.fromstring(z.read(n)) for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)]
        has_native_frame=any(r.findall('.//{*}header//{*}line') for r in roots)
        native='\n'.join(t.text or '' for r in roots for t in r.iter() if t.tag.endswith('}t'))
        tables=sum(1 for r in roots for t in r.iter() if t.tag.endswith('}tbl'))
        images={hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('BinData/')}
        forbidden_parts=[n for n in z.namelist() if 'masterpage' in n.lower()]
        if forbidden_parts: errors.append('OLD_MASTERPAGE_PRESENT')
        for name in z.namelist():
            if name.endswith(('.xml','.txt','.hpf')):
                package_text=z.read(name).decode('utf-8',errors='replace')
                if any(s in package_text for s in ('과학탐구','지구과학','PEAK','SOLVE_A','SOLVE_B','검수 PASS')):
                    errors.append('FORBIDDEN_PACKAGE_TEXT: '+name)
    locations=[]; missing=[]; rendered_units=0; native_units=0; figure_pixels=[]
    with fitz.open(pdf) as doc:
        text='\n'.join(p.get_text() for p in doc)
        columns=[]
        for pn,page in enumerate(doc,1):
            if has_native_frame and not has_page_frame(page): errors.append('RENDERED_PAGE_FRAME_MISSING: '+str(pn))
            if '편집 검토 초안' not in page.get_text(): errors.append('PAGE_HEADER_MISSING')
            if not(835<page.rect.width<850 and 1180<page.rect.height<1200):
                errors.append('NOT_A3_PORTRAIT')
            groups=[[],[]]
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    x0,y0,x1,y1=line['bbox']
                    if x0<0 or y0<0 or x1>page.rect.width or y1>page.rect.height:
                        errors.append('TEXT_OUTSIDE_PAGE')
                    value=''.join(s['text'] for s in line['spans'])
                    groups[int(x0>page.rect.width/2-8)].append((y0,x0,value))
            columns.extend((pn,c,normalized(''.join(v for _,_,v in sorted(g)))) for c,g in enumerate(groups))
        for ix,item in enumerate(items):
            units=student_units(item)
            excluded=[]
            for cond in item['student_view']['conditions']:
                graphic=display.get(item['item_id']+'|'+cond['condition_id'],{})
                lines=graphic.get('replace_lines',[])
                if lines:
                    for kind,data in parse_material('\n'.join(lines)):
                        excluded.extend([data] if kind=='text' else [c for row in data for c in row])
                if lines or graphic.get('insert_before_line') is not None:
                    if sha(Path(artifact_root)/graphic['png_path']) not in images:
                        errors.append('EMBEDDED_FIGURE_SHA_MISMATCH: '+item['item_id'])
                    matches=match_pdf_figure(doc,Path(artifact_root)/graphic['png_path'])
                    if len(matches)!=1:
                        errors.append('PDF_FIGURE_MISSING_CHANGED_OR_DUPLICATED: '+item['item_id'])
                    figure_pixels.append({'item':item['number'],'data_id':cond['condition_id'],'matches':matches})
            # A graphic substitutes only the exact declared source units.
            remaining=list(units)
            for unit in excluded:
                if unit not in remaining:
                    errors.append('UNDECLARED_FIGURE_REPLACEMENT: '+item['item_id'])
                else: remaining.remove(unit)
            native_units+=len(remaining); rendered_units+=len(excluded)
            for label,actual in [('HWPX',native),('PDF',text)]:
                try:
                    frame=item_frame(item,actual,items[ix+1] if ix+1<len(items) else None)
                except ValueError as exc:
                    errors.append(label+' '+str(item['number'])+' '+str(exc))
                    frame=''
                missing.extend({'item':item['number'],'surface':label,'text':u} for u in missing_units(remaining,frame))
            for c in CIRCLED:
                if c not in text: errors.append('CHOICE_MARKER_MISSING')
            prompt=normalized(f"{item['number']}. "+item['student_view']['prompt'])
            if normalized(native).count(prompt)!=1 or normalized(text).count(prompt)!=1:
                errors.append('ITEM_MISSING_OR_DUPLICATED: '+str(item['number']))
            found=[(pn,col) for pn,col,content in columns if prompt in content]
            if len(found)!=1: errors.append(f"PROMPT_LOCATION_{len(found)}: {item['number']}")
            else:
                pn,col=found[0]
                for fig in figure_pixels:
                    if fig['item']==item['number'] and fig['matches'] and (fig['matches'][0]['page'],fig['matches'][0]['column'])!=(pn,col+1):
                        errors.append('PDF_FIGURE_WRONG_ITEM_COLUMN: '+item['item_id'])
                last=normalized(CIRCLED[4]+' '+item['student_view']['choices'][4])
                column_text=next(v for p,c,v in columns if (p,c)==(pn,col))
                following=items[ix+1] if ix+1<len(items) else None
                next_prompt=normalized(f"{following['number']}. "+following['student_view']['prompt']) if following else ''
                try:
                    item_frame(item,column_text,following if next_prompt and next_prompt in column_text else None)
                    same_column=True
                except ValueError:
                    same_column=False
                if not same_column:
                    errors.append('ITEM_SPLIT_ACROSS_COLUMNS: '+str(item['number']))
                locations.append({'number':item['number'],'page':pn,'column':col+1,
                                  'whole_item_same_column':same_column})
            for field in ('rationale',):
                teacher=item.get('teacher',{}).get(field,'')
                if teacher and normalized(teacher) in normalized(text):
                    errors.append('TEACHER_TEXT_EXPOSED: '+item['item_id'])
        if [(i['page'],i['column']) for i in locations] != sorted((i['page'],i['column']) for i in locations):
            errors.append('READING_ORDER_INVALID')
        fonts={}
        for page in doc:
            for f in page.get_fonts(full=True):
                name,ext,kind,data=doc.extract_font(f[0])
                fonts[name]={'embedded':bool(data),'type':kind}
        if any(not f['embedded'] for f in fonts.values()): errors.append('UNEMBEDDED_FONT')
        pages=len(doc)
    if missing: errors.append('SOURCE_TEXT_MISSING')
    return {'mechanical_status':'PASS' if not errors else 'FAIL','errors':errors,
        'item_count':len(items),'page_count':pages,'target_pages':6,'target_met':pages==6,
        'native_table_count':tables,'native_source_units_checked':native_units,
        'graphic_source_units_bound':rendered_units,'missing_source_units':missing,
        'locations':locations,'fonts':fonts,'human_release_approval':None,
        'pdf_figure_pixel_checks':figure_pixels,
        'page_frame_checked':has_native_frame,
        'visual_semantic_review':'REQUIRES_PAGE_AND_FIGURE_REVIEW'}
