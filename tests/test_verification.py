import os
import json
from pathlib import Path
import pytest
import press_verify as verify

def test_page_frame_requires_rendered_header_and_full_height_divider():
    import fitz
    d=fitz.open();p=d.new_page(width=842,height=1189)
    p.draw_line((71,116),(737,116))
    p.draw_line((404,224),(404,740))
    assert not verify.has_page_frame(p)
    p.draw_line((404,224),(404,1069))
    assert verify.has_page_frame(p)

def test_return_verifier_rejects_missing_or_changed_files(tmp_path):
    (tmp_path/'a.txt').write_text('original',encoding='utf-8')
    manifest=verify.make_manifest(tmp_path, {'items_sha256':'a'*64})
    verify.verify_manifest(tmp_path,manifest)
    (tmp_path/'a.txt').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError,match='SHA'):
        verify.verify_manifest(tmp_path,manifest)
    (tmp_path/'a.txt').unlink()
    with pytest.raises(ValueError,match='MISSING'):
        verify.verify_manifest(tmp_path,manifest)

def test_manifest_rejects_escape(tmp_path):
    with pytest.raises(ValueError,match='PATH'):
        verify.verify_manifest(tmp_path,{'files':[{'path':'../secret','sha256':'a'*64}]})

@pytest.mark.parametrize('extra_path',['extra.txt','nested/return-manifest.json'])
def test_return_verifier_rejects_unlisted_extra_file(tmp_path,extra_path):
    (tmp_path/'a.txt').write_text('bound',encoding='utf-8')
    manifest=verify.make_manifest(tmp_path, {'items_sha256':'a'*64})
    extra=tmp_path/extra_path;extra.parent.mkdir(parents=True,exist_ok=True)
    extra.write_text('unlisted',encoding='utf-8')
    with pytest.raises(ValueError,match='COVERAGE'):
        verify.verify_manifest(tmp_path,manifest)

def test_return_verifier_rejects_duplicate_entries_and_wrong_size(tmp_path):
    (tmp_path/'a.txt').write_text('bound',encoding='utf-8')
    manifest=verify.make_manifest(tmp_path, {'items_sha256':'a'*64})
    manifest['files'].append(dict(manifest['files'][0]))
    with pytest.raises(ValueError,match='DUPLICATE'):
        verify.verify_manifest(tmp_path,manifest)
    manifest['files'].pop()
    manifest['files'][0]['bytes']+=1
    with pytest.raises(ValueError,match='SIZE'):
        verify.verify_manifest(tmp_path,manifest)

def test_return_manifest_rejects_symlinked_files(tmp_path):
    root_manifest=tmp_path/'return-manifest.json';root_manifest.write_text('{}',encoding='utf-8')
    nested=tmp_path/'nested';nested.mkdir()
    link=nested/'return-manifest.json'
    try:
        link.symlink_to(root_manifest)
    except OSError as exc:
        pytest.skip(f'symlinks unavailable: {exc}')
    with pytest.raises(ValueError,match='SYMLINK'):
        verify.make_manifest(tmp_path, {'items_sha256':'a'*64})

def test_return_manifest_rejects_root_manifest_symlink(tmp_path):
    target=tmp_path/'target.json';target.write_text('{}',encoding='utf-8')
    link=tmp_path/'return-manifest.json'
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f'symlinks unavailable: {exc}')
    with pytest.raises(ValueError,match='SYMLINK'):
        verify.make_manifest(tmp_path, {'items_sha256':'a'*64})

def test_table_missing_cell_is_found_even_when_other_units_exist():
    missing=verify.missing_units(['시점','2030년','2032년'], '시점 2030년')
    assert missing == ['2032년']

def test_item_frame_checks_marker_order_and_points():
    item={'number':1,'points':2,'student_view':{'prompt':'옳은 것은?', 'choices':['갑','을','병','정','무']}}
    actual='1. 옳은 것은? [2점]\n① 갑\n② 을\n③ 병\n④ 정\n⑤ 무'
    assert verify.item_frame(item,actual).endswith('⑤무')
    item['student_view']['choices'][:2]=['을','갑']
    with pytest.raises(ValueError,match='CHOICE_ORDER'):
        verify.item_frame(item,actual)
    item['student_view']['choices'][:2]=['갑','을']; item['points']=99
    with pytest.raises(ValueError,match='STEM_POINTS'):
        verify.item_frame(item,actual)

@pytest.mark.integration
def test_visual_display_cannot_swap_another_items_valid_picture(tmp_path):
    from copy import deepcopy
    from press_contract import load_packet
    from press_visuals import build_visuals
    forge=Path(os.environ.get('PRESS_FORGE_ROOT', Path(__file__).resolve().parents[2]/'integrated-social-item-forge'))
    packet=load_packet(forge,'FRG-SOC-2028-M01')
    result=build_visuals(packet['visual_handoff'],tmp_path,'b'*40)
    verify.validate_visual_result(packet['visual_handoff'],result,tmp_path)
    keys=list(result['display'])
    changed=deepcopy(result)
    changed['display'][keys[0]]['png_path']=changed['display'][keys[1]]['png_path']
    with pytest.raises(ValueError,match='DISPLAY'):
        verify.validate_visual_result(packet['visual_handoff'],changed,tmp_path)

def test_pdf_figure_check_rejects_transparent_replacement(tmp_path):
    import fitz
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(160,80),'white')
    ImageDraw.Draw(image).rectangle((10,10,130,55),fill='black')
    path=tmp_path/'figure.png'; image.save(path)
    pdf=fitz.open(); page=pdf.new_page()
    xref=page.insert_image(fitz.Rect(30,30,190,110),filename=str(path))
    assert verify.match_pdf_figure(pdf,path)
    page.delete_image(xref)
    assert verify.match_pdf_figure(pdf,path)==[]
