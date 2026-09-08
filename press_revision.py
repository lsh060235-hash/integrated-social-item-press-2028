"""Read-only revision ZIP intake and explicitly unapproved review-draft production."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from press_contract import _forge_api, ContractError

ROOT=Path(__file__).resolve().parent

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
    manifest=json.loads(members['delivery_manifest.json'])
    entries=manifest['files']
    if len(entries)!=len({f['path'] for f in entries}) or {f['path'] for f in entries}|{'delivery_manifest.json'}!=set(names):
        raise ContractError('MEMBER_COVERAGE_MISMATCH')
    for f in entries:
        data=members[f['path']]
        if hashlib.sha256(data).hexdigest()!=f['sha256'] or len(data)!=f['size']:
            raise ContractError('MEMBER_HASH_MISMATCH: '+f['path'])
    return members

def load_revision(archive,forge_root):
    """Accept draft production without importing an earlier version's approval."""
    _,build_visual_handoff,canonical_sha256=_forge_api(Path(forge_root))
    from integrated_social_forge.review_packets import build_review_packets
    from integrated_social_forge.review_collection import collect_review_results
    members=read_archive(archive)
    def get(name): return json.loads(members[name])
    delivery=get('delivery_manifest.json')
    items,specs,blueprint=[get(n+'.json') for n in ('items','item_specs','blueprint')]
    campaign=delivery['campaign_id']
    if (not re.fullmatch(r'FRG-SOC-2028-M0[12]',campaign) or blueprint['campaign_id']!=campaign
        or blueprint['subject']!='통합사회' or len(items)!=25 or len(specs)!=25
        or [p['item_no'] for p in blueprint['items']]!=list(range(1,26))
        or sum(p['points'] for p in blueprint['items'])!=50):
        raise ContractError('REVISION_IDENTITY_MISMATCH')
    canonical={n+'_sha256':canonical_sha256(v) for n,v in [('items',items),('item_specs',specs),('blueprint',blueprint)]}
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
        'edition_label':campaign+' · 표현교정 '+delivery['version'].split('-')[-1],
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

def build_revision(archive,forge_root,out):
    from press import write_json
    from press_layout import build_hwpx,render_hangul
    from press_visuals import build_revision_visuals
    from press_verify import verify_exam,preview_pdf,validate_visual_result,missing_units,sha
    import fitz
    packet=load_revision(archive,forge_root)
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
    result=build_revision_visuals(packet['visual_handoff'],out/'figures',commit)
    write_json(out/'visual-result.json',result)
    write_json(out/'visual-handoff.json',packet['visual_handoff'])
    write_json(out/'visual-receipt.json',result['receipt'])
    write_json(out/'visual-artifacts.json',result['artifacts'])
    bytes_report=validate_visual_result(packet['visual_handoff'],result,out/'figures')
    render={}
    pilot_numbers=[2,13] if packet['campaign_id'].endswith('M01') else [2,5]
    for group,teacher,numbers in [('pilot',False,pilot_numbers),('student',False,None),('teacher',True,None)]:
        folder=out/group; folder.mkdir()
        stem={'pilot':'two-items','student':'exam','teacher':'solutions'}[group]
        hwpx,pdf=folder/(stem+'.hwpx'),folder/(stem+'.pdf')
        build_hwpx(packet,hwpx,numbers,teacher=teacher,
            visuals=None if teacher else result,artifact_root=out/'figures',
            column_starts=(25,) if group=='student' and packet['campaign_id'].endswith('M02') else ())
        render[group]=render_hangul(hwpx,pdf)
        preview_pdf(pdf,out/'preview'/group)
        if teacher:
            with fitz.open(pdf) as d:
                text='\n'.join(p.get_text() for p in d)
                units=[]
                for item in packet['items']:
                    t=item['teacher']
                    units.extend([t['rationale']]+[s['operation'] for s in t['solution_steps']]
                                 +[e['refutation'] for e in t['choice_evaluations'] if e.get('refutation')])
                if missing_units(units,text): raise ContractError('SOLUTION_TEXT_MISSING')
        else:
            check=verify_exam(packet,hwpx,pdf,result,out/'figures',numbers)
            if check['mechanical_status']!='PASS': raise ContractError('RENDER_VERIFICATION_FAILED: '+repr(check['errors']))
            write_json(folder/'verification.json',check)
        print(packet['campaign_id'],group,render[group]['pages'],'pages PASS',flush=True)
    key='\n'.join(f"{i['number']}. {i['teacher']['answer']} ({i['points']:g}점)" for i in packet['items'])
    (out/'teacher/answer-key.txt').write_text(key+'\n',encoding='utf-8')
    validate_revision(packet,archive,forge_root)
    verification=json.loads((out/'student/verification.json').read_text(encoding='utf-8'))
    verification.update({'render':render,'visual_file_check':bytes_report,'press_commit':commit,
        'source_status':packet['status'],'source_binding':packet['binding'],
        'agent_page_review':'PENDING','human_release_approval':None})
    write_json(out/'verification.json',verification)
    print('DRAFT BUILT: all pages require visual review before seal.',flush=True)

def seal_revision(archive,forge_root,out):
    from press import write_json
    from press_verify import verify_exam,validate_visual_result,make_manifest,verify_manifest,sha
    import fitz
    out=Path(out).resolve()
    packet=json.loads((out/'input-packet.json').read_text(encoding='utf-8'))
    validate_revision(packet,archive,forge_root)
    if sha(out/'source-input.zip')!=packet['binding']['source_zip_sha256']:
        raise ContractError('SOURCE_COPY_MISMATCH')
    result=json.loads((out/'visual-result.json').read_text(encoding='utf-8'))
    validate_visual_result(packet['visual_handoff'],result,out/'figures')
    check=verify_exam(packet,out/'student/exam.hwpx',out/'student/exam.pdf',result,out/'figures')
    if check['mechanical_status']!='PASS': raise ContractError('SEAL_VERIFICATION_FAILED')
    review=json.loads((out/'agent-page-review.json').read_text(encoding='utf-8'))
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
    parser.add_argument('command',choices=['build','seal','verify'])
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--forge-root',type=Path,default=ROOT.parent/'integrated-social-item-forge')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='verify':
        from press_verify import verify_manifest
        verify_manifest(args.out,json.loads((args.out/'return-manifest.json').read_text(encoding='utf-8')))
        print('ALL RETURN FILE BYTES VERIFIED; human approval is separate.')
    else:
        if not args.archive: parser.error('--archive is required')
        (build_revision if args.command=='build' else seal_revision)(args.archive,args.forge_root,args.out)

if __name__=='__main__': main()
