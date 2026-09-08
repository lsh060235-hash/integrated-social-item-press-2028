"""Mechanical verification is evidence, never a human publication approval."""
from __future__ import annotations
import hashlib
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


def verify_exam(packet,hwpx,pdf,visual_result,artifact_root,item_numbers=None):
    items=[i for i in packet['items'] if item_numbers is None or i['number'] in item_numbers]
    display=visual_result.get('display',{})
    errors=[]
    with zipfile.ZipFile(hwpx) as z:
        roots=[ET.fromstring(z.read(n)) for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)]
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
                end=[(p,c) for p,c,v in columns if last in v]
                locations.append({'number':item['number'],'page':pn,'column':col+1,
                                  'whole_item_same_column':(pn,col) in end})
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
        'visual_semantic_review':'REQUIRES_PAGE_AND_FIGURE_REVIEW'}
