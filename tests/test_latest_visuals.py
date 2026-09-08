import json, os, zipfile
from pathlib import Path
import pytest
import press_visuals as v

BUNDLES=Path(os.environ.get('PRESS_DELIVERY_ROOT',Path(__file__).parents[2]/'integrated-social-item-forge/deliveries/2026-09-08-language-v2'))

def load(round):
    with zipfile.ZipFile(next(BUNDLES.glob(round+'*.zip'))) as z:
        return json.loads(z.read('press/visual_handoff.json'))

@pytest.mark.integration
@pytest.mark.skipif(not BUNDLES.is_dir(),reason='private latest manuscripts unavailable')
def test_latest_rounds_are_source_bound_and_render_all_requests(tmp_path):
    for campaign,count in [('M01',18),('M02',19),('M03',14)]:
        request=load(campaign)
        plan=v.make_visual_plan(request)
        assert all(f['mode'] for f in plan['figures'])
        result=v.build_revision_visuals(request,tmp_path/campaign,'a'*40,plan)
        assert len(result['artifacts'])==count
        if campaign=='M03':
            specs={a['item_id'][-3:]+'|'+a['data_id']:json.loads((tmp_path/campaign/a['figure_spec_path']).read_text(encoding='utf-8')) for a in result['artifacts']}
            sources={e['item_id'][-3:]+'|'+e['data_id']:e['source_content'].splitlines() for e in request['requests']}
            paired=v._table_rows(sources['Q03|MAP-A'])[1]
            assert specs['Q03|MAP-A']['core_variables']['topology']['panels'][0]['rows']==paired[:2]
            routes=v._table_rows(sources['Q12|BORDER-A'])[1][1:]
            assert specs['Q12|BORDER-A']['core_variables']['topology']['routes']==[[r[0],r[1],r[2].split('→')] for r in routes]
            for key in ('Q09|DIGITAL-A','Q13|RESULT-B','Q19|DATA-A'):
                assert specs[key]['core_variables']['table_rows']==v._table_rows(sources[key])[1]


def test_signed_bar_uses_font_supported_negative_sign():
    from PIL import ImageFont
    topology={'rows':[['group','change'],['export','35'],['import','-14']],'values':[35,-14]}
    _,ops=v._m03_ops('revision_trade',topology,ImageFont.load_default())
    assert any(op[0]=='text' and op[3]=='-14' for op in ops)
    bars=[op for op in ops if op[0]=='rect']
    assert bars[1][1]<bars[0][1]==bars[1][3]
    assert (bars[0][3]-bars[0][1])/(bars[1][3]-bars[1][1])==pytest.approx(35/14)


def test_temperature_chart_keeps_present_baseline_distinct_from_future_scenario():
    from PIL import ImageFont
    topology={'rows':[['month','1','2'],['current','11','13']], 'values':[[11,13]]}
    _,ops=v._m03_ops('revision_temperature',topology,ImageFont.load_default())
    assert any(op[0]=='text' and '현재' in op[3] for op in ops)
