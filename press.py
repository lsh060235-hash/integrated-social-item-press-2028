"""Local draft build and hash return. No Forge status write, export, or publication."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import zipfile
import shutil
from pathlib import Path
sys.dont_write_bytecode=True
from press_contract import load_packet, validate_packet
from press_layout import build_hwpx, render_hangul
from press_visuals import build_visuals
from press_verify import (make_manifest, verify_manifest, verify_exam, preview_pdf,
                          validate_visual_result, missing_units, sha)

ROOT=Path(__file__).resolve().parent


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build(config,out):
    config=json.loads(Path(config).read_text(encoding='utf-8-sig'))
    forge=Path(config['forge_root']).resolve()
    packet=load_packet(forge,config.get('campaign_id','FRG-SOC-2028-M01'))
    validate_packet(packet,forge)
    out=Path(out).resolve()
    if out.exists(): raise ValueError('OUTPUT_EXISTS: use a new output directory')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    # Receipts name the exact committed generator, never a guessed or future SHA.
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
    if dirty.strip(): raise ValueError('GENERATOR_NOT_COMMITTED')
    out.mkdir(parents=True)
    for name in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines():
        target=out/'reproduction'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    write_json(out/'input-packet.json',packet)
    write_json(out/'visual-handoff.json',packet['visual_handoff'])
    result=build_visuals(packet['visual_handoff'],out/'figures',commit)
    write_json(out/'visual-result.json',result)
    write_json(out/'visual-receipt.json',result['receipt'])
    write_json(out/'visual-artifacts.json',result['artifacts'])
    bytes_report=validate_visual_result(packet['visual_handoff'],result,out/'figures')
    render={}
    pilot=out/'pilot'; pilot.mkdir()
    build_hwpx(packet,pilot/'two-items.hwpx',[2,13],visuals=result,artifact_root=out/'figures')
    render['pilot']=render_hangul(pilot/'two-items.hwpx',pilot/'two-items.pdf')
    pcheck=verify_exam(packet,pilot/'two-items.hwpx',pilot/'two-items.pdf',result,out/'figures',[2,13])
    write_json(pilot/'verification.json',pcheck)
    preview_pdf(pilot/'two-items.pdf',pilot/'preview')
    if pcheck['mechanical_status']!='PASS': raise ValueError('PILOT_FAILED')
    print('PILOT PASS',flush=True)
    student=out/'student'; student.mkdir()
    build_hwpx(packet,student/'exam.hwpx',visuals=result,artifact_root=out/'figures')
    render['exam']=render_hangul(student/'exam.hwpx',student/'exam.pdf')
    report=verify_exam(packet,student/'exam.hwpx',student/'exam.pdf',result,out/'figures')
    preview_pdf(student/'exam.pdf',out/'preview'/'exam')
    print('EXAM',report['page_count'],'pages',report['mechanical_status'],flush=True)
    teacher=out/'teacher'; teacher.mkdir()
    build_hwpx(packet,teacher/'solutions.hwpx',teacher=True)
    render['solutions']=render_hangul(teacher/'solutions.hwpx',teacher/'solutions.pdf')
    preview_pdf(teacher/'solutions.pdf',out/'preview'/'solutions')
    import fitz
    with fitz.open(teacher/'solutions.pdf') as d:
        text='\n'.join(p.get_text() for p in d)
        omitted=missing_units([i['teacher']['rationale'] for i in packet['items']],text)
        if omitted: raise ValueError('SOLUTION_RATIONALE_MISSING')
    key='\n'.join(f"{i['number']}. {i['teacher']['answer']} ({i['points']:g}점)" for i in packet['items'])
    (teacher/'answer-key.txt').write_text(key+'\n',encoding='utf-8')
    validate_packet(packet,forge)
    validate_visual_result(packet['visual_handoff'],result,out/'figures')
    report.update({'render':render,'visual_file_check':bytes_report,'press_commit':commit,
        'source_binding':packet['binding'],'agent_page_review':'PENDING',
        'reviewed_pdf_sha256':None,'human_release_approval':None})
    write_json(out/'verification.json',report)
    if report['mechanical_status']!='PASS': raise ValueError('EXAM_VALIDATION_FAILED: '+repr(report['errors']))
    print('DRAFT BUILT. Inspect all PNG pages before sealing.',flush=True)


def seal(config,out):
    out=Path(out).resolve()
    config=json.loads(Path(config).read_text(encoding='utf-8-sig'))
    packet=json.loads((out/'input-packet.json').read_text(encoding='utf-8'))
    validate_packet(packet,Path(config['forge_root']).resolve())
    result=json.loads((out/'visual-result.json').read_text(encoding='utf-8'))
    validate_visual_result(packet['visual_handoff'],result,out/'figures')
    check=verify_exam(packet,out/'student'/'exam.hwpx',out/'student'/'exam.pdf',result,out/'figures')
    if check['mechanical_status']!='PASS': raise ValueError('SEAL_VERIFICATION_FAILED')
    review=json.loads((out/'agent-page-review.json').read_text(encoding='utf-8'))
    if review['exam_pdf_sha256']!=sha(out/'student'/'exam.pdf') or review['exam_pages_reviewed']!=list(range(1,check['page_count']+1)):
        raise ValueError('STALE_OR_INCOMPLETE_PAGE_REVIEW')
    import fitz
    with fitz.open(out/'teacher'/'solutions.pdf') as d:
        if review['solutions_pdf_sha256']!=sha(out/'teacher'/'solutions.pdf') or review['solutions_pages_reviewed']!=list(range(1,len(d)+1)):
            raise ValueError('STALE_OR_INCOMPLETE_SOLUTION_REVIEW')
    manifest=make_manifest(out,packet['binding'])
    write_json(out/'return-manifest.json',manifest)
    verify_manifest(out,manifest)
    archive=out.with_suffix('.zip')
    if archive.exists(): raise ValueError('ARCHIVE_EXISTS')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(out).as_posix())
    archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
    print('SEALED',archive,flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','seal','verify'])
    parser.add_argument('--config',default='config.local.json')
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='build': build(args.config,args.out)
    elif args.command=='seal': seal(args.config,args.out)
    else:
        out=Path(args.out); verify_manifest(out,json.loads((out/'return-manifest.json').read_text(encoding='utf-8')))
        print('ALL RETURN FILE BYTES VERIFIED; human approval is separate.')


if __name__=='__main__':
    main()
