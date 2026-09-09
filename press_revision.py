"""Read-only revision ZIP intake and explicitly unapproved review-draft production."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import platform
from importlib.metadata import version
import zipfile
from pathlib import Path
from press_contract import _forge_api, ContractError

ROOT=Path(__file__).resolve().parent


def apply_student_editorial(packet,overlay):
    if (not isinstance(overlay,dict)
        or overlay.get('schema_version')!='press-student-editorial-v0.1'
        or overlay.get('campaign_id')!=packet['campaign_id']
        or overlay.get('source_version')!=packet['source_version']
        or overlay.get('source_items_sha256')!=packet['binding']['canonical_artifacts']['items_sha256']):
        raise ContractError('STUDENT_EDITORIAL_SOURCE_MISMATCH')
    entries=overlay.get('conditions')
    if not isinstance(entries,list) or not entries:
        raise ContractError('STUDENT_EDITORIAL_CONDITIONS_REQUIRED')
    result=copy.deepcopy(packet)
    conditions={(item['item_id'],condition['condition_id']):condition
                for item in result['items'] for condition in item['student_view']['conditions']}
    seen=set()
    required={'item_id','condition_id','source_content_sha256','content'}
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!=required:
            raise ContractError('STUDENT_EDITORIAL_ENTRY_INVALID')
        key=entry['item_id'],entry['condition_id']
        if key in seen: raise ContractError('STUDENT_EDITORIAL_DUPLICATE')
        seen.add(key)
        condition=conditions.get(key)
        if condition is None: raise ContractError('STUDENT_EDITORIAL_CONDITION_UNKNOWN')
        if (not isinstance(entry['source_content_sha256'],str)
            or not isinstance(entry['content'],str)):
            raise ContractError('STUDENT_EDITORIAL_CONTENT_MISMATCH')
        source_sha=hashlib.sha256(condition['content'].encode('utf-8')).hexdigest()
        if entry['source_content_sha256']!=source_sha:
            raise ContractError('STUDENT_EDITORIAL_CONTENT_MISMATCH')
        condition['content']=entry['content']
    return result


def validate_student_editorial_visuals(packet,plan):
    """Keep every source line used by a bound visual unchanged."""
    conditions={(item['item_id'],condition['condition_id']):condition['content'].splitlines()
                for item in packet['items'] for condition in item['student_view']['conditions']}
    for figure in plan['figures']:
        lines=conditions.get((figure['item_id'],figure['data_id']))
        if lines is None:
            raise ContractError('STUDENT_EDITORIAL_VISUAL_SOURCE_MISSING')
        for selector in figure['lines']:
            text=selector.get('text') if isinstance(selector,dict) else selector
            occurrence=selector.get('occurrence') if isinstance(selector,dict) else 0
            matches=[n for n,line in enumerate(lines) if line==text]
            if (not isinstance(text,str) or type(occurrence) is not int
                or not 0<=occurrence<len(matches)
                or (isinstance(selector,str) and len(matches)!=1)):
                raise ContractError('STUDENT_EDITORIAL_VISUAL_SOURCE_CHANGED')


def augment_student_table_visuals(packet,production_packet,plan):
    """Rasterize source-bound tables after an editorial reflow changes pagination."""
    request=copy.deepcopy(packet['visual_handoff'])
    result_plan=copy.deepcopy(plan)
    figures={(figure['item_id'],figure['data_id']):figure
             for figure in result_plan['figures']}
    preserve=['labels','values','units','legends','spatial_and_temporal_relations']
    for item in production_packet['items']:
        for condition in item['student_view']['conditions']:
            source=condition['content']
            lines=source.splitlines()
            indices=[n for n,line in enumerate(lines) if '|' in line]
            if not indices:
                continue
            key=item['item_id'],condition['condition_id']
            figure=figures.get(key)
            if figure is not None:
                if figure['mode']=='table':
                    figure['replace']=True
                continue
            digest=hashlib.sha256(source.encode('utf-8')).hexdigest()
            request['requests'].append({'item_id':key[0],'data_id':key[1],
                'material_kind':'STATISTIC','data_grammar':['TABLE'],
                'source_content':source,'source_content_sha256':digest,'preserve':preserve})
            selectors=[]
            for n in indices:
                line=lines[n]
                selectors.append(line if lines.count(line)==1 else
                                 {'text':line,'occurrence':lines[:n].count(line)})
            figure={'item_id':key[0],'data_id':key[1],'source_content_sha256':digest,
                'mode':'table','lines':selectors,'replace':True}
            result_plan['figures'].append(figure)
            figures[key]=figure
    return request,result_plan


def write_visual_specs(out,source_plan,render_handoff,render_plan,student_editorial):
    """Keep the reusable source plan separate from editorial render inputs."""
    from press import write_json
    out=Path(out)
    write_json(out/'visual-plan.json',source_plan)
    if student_editorial is not None:
        write_json(out/'render-visual-plan.json',render_plan)
        write_json(out/'render-visual-handoff.json',render_handoff)


def verify_saved_plan(out):
    from press_verify import sha,verify_file_binding
    out=Path(out)
    verification=json.loads((out/'verification.json').read_text(encoding='utf-8'))
    if sha(out/'visual-plan.json')!=verification.get('visual_plan_sha256'):
        raise ContractError('VISUAL_PLAN_CHANGED_AFTER_BUILD')
    render_plan=out/'render-visual-plan.json'
    if render_plan.exists() or verification.get('render_visual_plan_sha256'):
        if (not render_plan.is_file()
            or sha(render_plan)!=verification.get('render_visual_plan_sha256')):
                raise ContractError('RENDER_VISUAL_PLAN_CHANGED_AFTER_BUILD')
    editorial=out/'solution-editorial.json'
    if editorial.exists() or verification.get('solution_editorial_sha256'):
        if not editorial.is_file() or sha(editorial)!=verification.get('solution_editorial_sha256'):
            raise ContractError('SOLUTION_EDITORIAL_CHANGED_AFTER_BUILD')
    student_editorial=out/'student-editorial.json'
    if student_editorial.exists() or verification.get('student_editorial_sha256'):
        if (not student_editorial.is_file()
            or sha(student_editorial)!=verification.get('student_editorial_sha256')):
                raise ContractError('STUDENT_EDITORIAL_CHANGED_AFTER_BUILD')
    render_handoff=out/'render-visual-handoff.json'
    if render_handoff.exists() or verification.get('render_visual_handoff_sha256'):
        if (not render_handoff.is_file()
            or sha(render_handoff)!=verification.get('render_visual_handoff_sha256')):
            raise ContractError('RENDER_VISUAL_HANDOFF_CHANGED_AFTER_BUILD')
    provenance=[out/'runtime.json']+[path for path in (out/'reproduction').rglob('*') if path.is_file()]
    expected={path.relative_to(out).as_posix() for path in provenance}
    verify_file_binding(out,verification.get('reproduction_files'),expected)


def forge_provenance(forge_root):
    """A copied runtime has no Git database; retain the original provenance there."""
    root=Path(forge_root).resolve()
    if (root/'press-runtime-provenance.json').is_file():
        return json.loads((root/'press-runtime-provenance.json').read_text(encoding='utf-8'))
    return {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())}

def read_archive(archive):
    """Validate names and manifest before exposing any member; never extract blindly."""
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):
            raise ContractError('DUPLICATE_ZIP_MEMBER')
        for n in names:
            if any(c in n for c in ('\\',':','\x00')) or any(p in ('','..','.') for p in n.split('/')):
                raise ContractError('UNSAFE_ZIP_MEMBER')
        members={n:z.read(n) for n in names}
    manifests=set(members)&{'delivery_manifest.json','FILE_MANIFEST.json'}
    if len(manifests)!=1: raise ContractError('AMBIGUOUS_OR_MISSING_MANIFEST')
    manifest_name=manifests.pop()
    manifest=json.loads(members[manifest_name])
    entries=([{'path':n,'sha256':digest} for n,digest in manifest.items()]
             if manifest_name=='FILE_MANIFEST.json' else manifest['files'])
    if len(entries)!=len({f['path'] for f in entries}) or {f['path'] for f in entries}|{manifest_name}!=set(names):
        raise ContractError('MEMBER_COVERAGE_MISMATCH')
    for f in entries:
        data=members[f['path']]
        if (hashlib.sha256(data).hexdigest()!=f['sha256'] or
            (manifest_name=='delivery_manifest.json' and len(data)!=f.get('size'))):
            raise ContractError('MEMBER_HASH_MISMATCH: '+f['path'])
    return members

def load_revision(archive,forge_root):
    """Accept draft production without importing an earlier version's approval."""
    _,build_visual_handoff,canonical_sha256=_forge_api(Path(forge_root))
    from integrated_social_forge.review_packets import build_review_packets
    from integrated_social_forge.review_collection import collect_review_results
    members=read_archive(archive)
    def get(name): return json.loads(members[name])
    aggregate='FILE_MANIFEST.json' in members
    if aggregate:
        status=get('DELIVERY_STATUS.json')
        delivery={'campaign_id':status['campaign_id'],
            'version':status['source_folder'].rsplit('/',1)[-1],
            'status':status['review_collection_status'],
            'human_approval':status['human_approval'],'blueprint_issue':status['blueprint_issue']}
    else:
        delivery=get('delivery_manifest.json')
    items,specs,blueprint=[get(n+'.json') for n in ('items','item_specs','blueprint')]
    campaign=delivery['campaign_id']
    if (not re.fullmatch(r'FRG-SOC-2028-M\d{2,}',campaign) or blueprint['campaign_id']!=campaign
        or blueprint['subject']!='통합사회' or len(items)!=25 or len(specs)!=25
        or [p['item_no'] for p in blueprint['items']]!=list(range(1,26))
        or sum(p['points'] for p in blueprint['items'])!=50):
        raise ContractError('REVISION_IDENTITY_MISMATCH')
    canonical={n+'_sha256':canonical_sha256(v) for n,v in [('items',items),('item_specs',specs),('blueprint',blueprint)]}
    if aggregate:
        # DELIVERY_STATUS is current; production_check can be a historical author snapshot.
        if any(status[k]!=v for k,v in canonical.items()):
            raise ContractError('SOURCE_HASH_MISMATCH')
        if status['item_count']!=25 or status['total_points']!=50:
            raise ContractError('REVISION_IDENTITY_MISMATCH')
        current=build_review_packets(items,campaign_id=campaign,item_specs=specs,
                                     review_profile=status['review_profile'])
        saved=get('reviews/review_packets.json')
        if len(saved)!=125 or saved!=current or canonical_sha256(saved)!=status['review_packets_sha256']:
            raise ContractError('REVIEW_PACKET_MISMATCH')
        reviews=get('reviews/review_results.json')
    else:
        check=get('production_check.json')
        pm=get('reviews/packets/manifest.json')
        if (delivery['items_canonical_sha256']!=canonical['items_sha256']
            or any(check[k]!=v for k,v in canonical.items())
            or pm['source_items_sha256']!=canonical['items_sha256']
            or pm['source_item_specs_sha256']!=canonical['item_specs_sha256']):
            raise ContractError('SOURCE_HASH_MISMATCH')
        current=build_review_packets(items,campaign_id=campaign,item_specs=specs,review_profile=pm.get('review_profile'))
        expected={f['file']:f for f in pm['packets']}
        if len(expected)!=125 or pm['packet_count']!=125:
            raise ContractError('REVIEW_COVERAGE_MISMATCH')
        reviews=[]
        for packet in current:
            relative=packet['item_id'][-3:]+'/'+packet['role']+'.json'
            saved=get('reviews/packets/'+relative)
            if saved!=packet or expected[relative]['packet_sha256']!=canonical_sha256(packet):
                raise ContractError('REVIEW_PACKET_MISMATCH: '+relative)
            reviews.append(get('reviews/results/'+relative))
    collection=collect_review_results(items,reviews,current)
    if collection['errors'] or collection!=get('reviews/collection_report.json'):
        raise ContractError('REVIEW_COLLECTION_MISMATCH')
    conditional=sum(i['state']=='NEEDS_ADJUDICATION' for i in collection['items'])
    if aggregate:
        from collections import Counter
        verdicts={role:dict(Counter(i['verdicts'][role] for i in collection['items']))
                  for role in ('SOLVE_A','SOLVE_B','CONTENT','DIFFICULTY','NOVELTY')}
        passed=[i['item_id'] for i in collection['items'] if all(v=='PASS' for v in i['verdicts'].values())]
        if status['role_verdicts']!=verdicts or status['all_roles_pass_items']!=passed:
            raise ContractError('REVIEW_STATUS_MISMATCH')
        delivery['conditional_items']=conditional
    if (delivery['status']!=collection['status'] or delivery['conditional_items']!=conditional
        or collection['status'] not in ('NEEDS_ADJUDICATION','READY_FOR_HUMAN_APPROVAL')):
        raise ContractError('REVIEW_STATUS_MISMATCH')
    visual=build_visual_handoff(items,specs,campaign_id=campaign)
    if visual!=get('press/visual_handoff.json'):
        raise ContractError('VISUAL_SOURCE_MISMATCH')
    by_spec={s['item_spec_id']:s for s in specs}
    if len(by_spec)!=25: raise ContractError('DUPLICATE_SPEC')
    entries=[]
    for item,plan in zip(items,blueprint['items'],strict=True):
        if (item['item_id']!=f"{campaign}-Q{plan['item_no']:02d}"
            or item['item_spec_id']!=plan['item_spec_id'] or len(item['student_view']['choices'])!=5
            or plan['points'] not in (1.5,2,2.5)):
            raise ContractError('ITEM_BLUEPRINT_MISMATCH')
        entries.append({'number':plan['item_no'],'points':plan['points'],'item_id':item['item_id'],
            'source_item_sha256':canonical_sha256(item),'item_revision':delivery['version'],
            'student_view':item['student_view'],
            'teacher':{k:item[k] for k in ('answer','rationale','solution_steps','choice_evaluations')},
            'materials':item['materials'],'core_data_relations':by_spec[item['item_spec_id']]['core_data_relations']})
    return {'schema_version':'integrated-social-press-revision-input-v0.1',
        'campaign_id':campaign,'subject':'통합사회','curriculum_revision':'2022',
        'source_version':delivery['version'],
        'edition_label':(f"제{int(campaign.rsplit('M',1)[1])}회 · 원고 {delivery['version']}" if aggregate else
                         campaign+' · 표현교정 '+delivery['version'].split('-')[-1]),
        'official_forge_export':False,'human_release_approval':None,
        'status':{'content_status':collection['status'],'conditional_items':conditional,
            'human_approval':delivery['human_approval'],'blueprint_issue':delivery['blueprint_issue'],
            'press_status':'DRAFT_ONLY','review_collection':collection},
        'items':entries,'visual_handoff':visual,
        'binding':{'hash_algorithm':'SHA-256','canonical_artifacts':canonical,
            'source_zip_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            'source_version':delivery['version'],'source_zip_filename':Path(archive).name,
            'visual_handoff_sha256':canonical_sha256(visual),
            'files':[{'path':n,'sha256':hashlib.sha256(data).hexdigest()} for n,data in sorted(members.items())]}}

def validate_revision(packet,archive,forge_root):
    if packet!=load_revision(archive,forge_root):
        raise ContractError('REVISION_PACKET_MISMATCH')

def build_revision(archive,forge_root,out,visual_plan=None,reference_pdf=None,reference_map=None,
                   solution_overlay=None,student_overlay=None):
    from press import write_json
    from press_layout import build_hwpx,render_hangul
    from press_visuals import build_revision_visuals,make_visual_plan,compile_visual_plan
    from press_verify import (verify_exam,preview_pdf,validate_visual_result,missing_units,sha,
                              build_item_review,balance_last_column,make_file_binding,
                              visual_font_manifest)
    import fitz
    from press_solutions import apply_editorial,verify_solutions
    packet=load_revision(archive,forge_root)
    student_editorial=(json.loads(Path(student_overlay).read_text(encoding='utf-8-sig'))
                       if student_overlay else None)
    production_packet=(apply_student_editorial(packet,student_editorial)
                       if student_editorial is not None else packet)
    editorial=json.loads(Path(solution_overlay).read_text(encoding='utf-8-sig')) if solution_overlay else None
    teacher_packet=(apply_editorial(production_packet,editorial)
                    if editorial is not None else production_packet)
    source_plan=(json.loads(Path(visual_plan).read_text(encoding='utf-8-sig')) if visual_plan else
                 make_visual_plan(packet['visual_handoff']))
    compile_visual_plan(packet['visual_handoff'],source_plan)
    render_handoff=packet['visual_handoff']
    render_plan=source_plan
    if student_editorial is not None:
        render_handoff,render_plan=augment_student_table_visuals(
            packet,production_packet,source_plan)
        compile_visual_plan(render_handoff,render_plan)
    validate_student_editorial_visuals(production_packet,render_plan)
    render_packet=copy.deepcopy(production_packet)
    render_packet['visual_handoff']=render_handoff
    out=Path(out).resolve()
    if out.exists(): raise ContractError('OUTPUT_EXISTS')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ContractError('GENERATOR_NOT_COMMITTED')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    out.mkdir(parents=True)
    shutil.copyfile(archive,out/'source-input.zip')
    for n in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines():
        dest=out/'reproduction'/n
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/n,dest)
    write_json(out/'input-packet.json',packet)
    if student_editorial is not None: write_json(out/'student-editorial.json',student_editorial)
    if editorial is not None: write_json(out/'solution-editorial.json',editorial)
    write_visual_specs(out,source_plan,render_handoff,render_plan,student_editorial)
    result=build_revision_visuals(render_handoff,out/'figures',commit,render_plan)
    write_json(out/'visual-result.json',result)
    write_json(out/'visual-handoff.json',packet['visual_handoff'])
    write_json(out/'visual-receipt.json',result['receipt'])
    write_json(out/'visual-artifacts.json',result['artifacts'])
    bytes_report=validate_visual_result(render_handoff,result,out/'figures')
    render={}
    # Exercise two distinct visible figure families when possible.
    pilot_numbers=[]; modes=set()
    for figure in render_plan['figures']:
        number=int(figure['item_id'].rsplit('Q',1)[1])
        if figure['mode'] not in modes and number not in pilot_numbers:
            pilot_numbers.append(number); modes.add(figure['mode'])
        if len(pilot_numbers)==2: break
    for item in packet['items']:
        if len(pilot_numbers)==2: break
        if item['number'] not in pilot_numbers: pilot_numbers.append(item['number'])
    adjustments=[]
    for group,teacher,numbers in [('pilot',False,pilot_numbers),('student',False,None),('teacher',True,None)]:
        folder=out/group; folder.mkdir()
        stem={'pilot':'two-items','student':'exam','teacher':'solutions'}[group]
        hwpx,pdf=folder/(stem+'.hwpx'),folder/(stem+'.pdf')
        build_hwpx(teacher_packet if teacher else render_packet,hwpx,numbers,teacher=teacher,
            visuals=None if teacher else result,artifact_root=out/'figures')
        render[group]=render_hangul(hwpx,pdf)
        if teacher:
            try:
                verify_solutions(teacher_packet,pdf)
            except ContractError as error:
                if not str(error).startswith('SOLUTION_ITEM_SPLIT'):
                    raise
                # A single final explanation takes priority over balanced column heights.
                build_hwpx(teacher_packet,hwpx,teacher=True,balance_solution_columns=False)
                render[group]=render_hangul(hwpx,pdf)
                verify_solutions(teacher_packet,pdf)
                adjustments.append({'reason':'solution_final_column_split','balance_solution_columns':False})
        else:
            check=verify_exam(production_packet,hwpx,pdf,result,out/'figures',numbers)
            if check['mechanical_status']!='PASS': raise ContractError('RENDER_VERIFICATION_FAILED: '+repr(check['errors']))
            starts=balance_last_column(check['locations']) if group=='student' else ()
            if starts:
                old_pages=render[group]['pages']
                build_hwpx(render_packet,hwpx,visuals=result,artifact_root=out/'figures',column_starts=starts)
                render[group]=render_hangul(hwpx,pdf)
                check=verify_exam(production_packet,hwpx,pdf,result,out/'figures')
                if check['mechanical_status']!='PASS' or render[group]['pages']!=old_pages:
                    raise ContractError('BALANCED_RENDER_VERIFICATION_FAILED')
                adjustments.append({'reason':'two_items_on_final_left_column','column_starts':starts})
            write_json(folder/'verification.json',check)
        preview_pdf(pdf,out/'preview'/group)
        print(packet['campaign_id'],group,render[group]['pages'],'pages PASS',flush=True)
    key='\n'.join(f"{i['number']}. {i['teacher']['answer']} ({i['points']:g}점)" for i in packet['items'])
    (out/'teacher/answer-key.txt').write_text(key+'\n',encoding='utf-8')
    validate_revision(packet,archive,forge_root)
    verification=json.loads((out/'student/verification.json').read_text(encoding='utf-8'))
    verification.update({'render':render,'visual_file_check':bytes_report,'press_commit':commit,
        'source_status':packet['status'],'source_binding':packet['binding'],
        'layout_adjustments':adjustments,'visual_plan_sha256':sha(out/'visual-plan.json'),
        'agent_page_review':'PENDING','human_release_approval':None})
    if editorial is not None: verification['solution_editorial_sha256']=sha(out/'solution-editorial.json')
    if student_editorial is not None:
        verification['student_editorial_sha256']=sha(out/'student-editorial.json')
        verification['render_visual_plan_sha256']=sha(out/'render-visual-plan.json')
        verification['render_visual_handoff_sha256']=sha(out/'render-visual-handoff.json')
    reference=None
    if reference_pdf:
        maps=json.loads(Path(reference_map or ROOT/'profiles/kice-reference-map.json').read_text(encoding='utf-8-sig'))
        reference={'pdf_sha256':maps['pdf_sha256'],'items':maps['campaigns'][packet['campaign_id']]}
    item_review=build_item_review(production_packet,out/'student/exam.pdf',out/'item-review',
                                 reference_pdf=reference_pdf,reference_map=reference)
    verification['largest_items']=sorted(item_review['items'],key=lambda i:i['height_pt'],reverse=True)[:5]
    provenance=forge_provenance(forge_root)
    runtime={'python':sys.version,'platform':platform.platform(),'press_commit':commit,
        'packages':{name:version(name) for name in ('python-hwpx','Pillow','PyMuPDF','jsonschema')},
        'forge_commit':provenance['commit'],'forge_dirty':provenance['dirty'],
        'forge_source_files':[],'fonts':[]}
    runtime['fonts'].extend(visual_font_manifest(result,out/'figures'))
    paths=list((Path(forge_root)/'src').rglob('*.py'))+list((Path(forge_root)/'schemas').rglob('*.json'))
    for path in sorted(paths):
        relative=path.relative_to(forge_root)
        dest=out/'reproduction/forge'/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest)
        runtime['forge_source_files'].append({'path':relative.as_posix(),'sha256':sha(path)})
    write_json(out/'reproduction/forge/press-runtime-provenance.json',provenance)
    for name in ('malgun.ttf','batang.ttc','HANBatang.ttf'):
        path=Path('C:/Windows/Fonts')/name
        if path.is_file(): runtime['fonts'].append({'name':name,'sha256':sha(path)})
    write_json(out/'runtime.json',runtime)
    provenance=[out/'runtime.json']+[path for path in (out/'reproduction').rglob('*') if path.is_file()]
    verification['reproduction_files']=make_file_binding(out,provenance)
    write_json(out/'verification.json',verification)
    print('DRAFT BUILT: all pages require visual review before seal.',flush=True)

def seal_revision(archive,forge_root,out):
    from press import write_json
    from press_verify import verify_exam,validate_visual_result,make_manifest,verify_manifest,sha,validate_item_review
    import fitz
    out=Path(out).resolve()
    verify_saved_plan(out)
    packet=json.loads((out/'input-packet.json').read_text(encoding='utf-8'))
    validate_revision(packet,archive,forge_root)
    from press_solutions import apply_editorial,verify_solutions
    student_editorial=out/'student-editorial.json'
    production_packet=(apply_student_editorial(
        packet,json.loads(student_editorial.read_text(encoding='utf-8')))
        if student_editorial.exists() else packet)
    render_plan_file=out/'render-visual-plan.json'
    plan=json.loads((render_plan_file if render_plan_file.exists() else
                     out/'visual-plan.json').read_text(encoding='utf-8'))
    validate_student_editorial_visuals(production_packet,plan)
    editorial=out/'solution-editorial.json'
    teacher_packet=(apply_editorial(
        production_packet,json.loads(editorial.read_text(encoding='utf-8')))
        if editorial.exists() else production_packet)
    verify_solutions(teacher_packet,out/'teacher/solutions.pdf')
    if sha(out/'source-input.zip')!=packet['binding']['source_zip_sha256']:
        raise ContractError('SOURCE_COPY_MISMATCH')
    result=json.loads((out/'visual-result.json').read_text(encoding='utf-8'))
    render_handoff=(json.loads((out/'render-visual-handoff.json').read_text(encoding='utf-8'))
                    if (out/'render-visual-handoff.json').exists() else packet['visual_handoff'])
    validate_visual_result(render_handoff,result,out/'figures')
    check=verify_exam(production_packet,out/'student/exam.hwpx',out/'student/exam.pdf',result,out/'figures')
    if check['mechanical_status']!='PASS': raise ContractError('SEAL_VERIFICATION_FAILED')
    review=json.loads((out/'agent-page-review.json').read_text(encoding='utf-8'))
    validate_item_review(production_packet,out/'student/exam.pdf',review)
    for key,path in [('exam','student/exam.pdf'),('solutions','teacher/solutions.pdf')]:
        with fitz.open(out/path) as d:
            if review[key+'_pdf_sha256']!=sha(out/path) or review[key+'_pages_reviewed']!=list(range(1,len(d)+1)):
                raise ContractError('STALE_OR_INCOMPLETE_PAGE_REVIEW')
    manifest=make_manifest(out,packet['binding'])
    write_json(out/'return-manifest.json',manifest)
    verify_manifest(out,manifest)
    dest=Path(str(out)+'.zip')
    if dest.exists(): raise ContractError('ARCHIVE_EXISTS')
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(out).as_posix())
    Path(str(dest)+'.sha256').write_text(sha(dest)+'  '+dest.name+'\n',encoding='ascii')
    print('SEALED',dest,flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','build','seal','verify'])
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--forge-root',type=Path,default=ROOT.parent/'integrated-social-item-forge')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--visual-plan',type=Path,help='Source-bound figure selectors exported by plan')
    parser.add_argument('--reference-pdf',type=Path,help='Local official reference PDF for per-item comparison')
    parser.add_argument('--reference-map',type=Path,help='Reference SHA, campaign mapping and crop coordinates')
    parser.add_argument('--solution-overlay',type=Path,help='Source-bound editorial explanations; preserves original teacher evidence')
    parser.add_argument('--student-overlay',type=Path,help='Source-bound condition wording edits; preserves original input packet')
    args=parser.parse_args()
    if args.command=='verify':
        from press_verify import verify_manifest
        verify_manifest(args.out,json.loads((args.out/'return-manifest.json').read_text(encoding='utf-8')))
        print('ALL RETURN FILE BYTES VERIFIED; human approval is separate.')
    else:
        if not args.archive: parser.error('--archive is required')
        if args.command=='plan':
            from press_visuals import make_visual_plan
            from press import write_json
            if args.out.exists(): raise ContractError('OUTPUT_EXISTS')
            packet=load_revision(args.archive,args.forge_root)
            write_json(args.out,make_visual_plan(packet['visual_handoff']))
        elif args.command=='build':
            build_revision(args.archive,args.forge_root,args.out,args.visual_plan,args.reference_pdf,
                           args.reference_map,args.solution_overlay,args.student_overlay)
        else:
            seal_revision(args.archive,args.forge_root,args.out)

if __name__=='__main__': main()
