import copy
import json
import subprocess
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

import press_visuals
from test_visuals import validate_visual_artifacts


ROOT = Path(__file__).parents[1]
BUNDLES = ROOT.parent / 'outputs' / 'social-language-20260908'
NS = {'s': 'http://www.w3.org/2000/svg'}


def request(campaign):
    with zipfile.ZipFile(next(BUNDLES.glob(f'*{campaign}*.zip'))) as bundle:
        return json.loads(bundle.read('press/visual_handoff.json'))


def test_revised_campaigns_build_all_requested_bound_assets(tmp_path):
    builder = getattr(press_visuals, 'build_revision_visuals', None)
    assert callable(builder), 'Revised campaign visual builder is required'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for campaign, count in [('M01', 18), ('M02', 19)]:
        source = request(campaign)
        root = tmp_path / campaign
        result = builder(source, root, commit)
        assert len(result['artifacts']) == count
        report = validate_visual_artifacts(source, result['receipt'], result['artifacts'], root)
        assert report['verified_binding_count'] == count
        for artifact, entry in zip(result['artifacts'], source['requests']):
            spec = json.loads((root / artifact['figure_spec_path']).read_text(encoding='utf-8'))
            assert spec['source_content'] == entry['source_content']
            display = result['display'][entry['item_id'] + '|' + entry['data_id']]
            assert all(line in entry['source_content'].splitlines() for line in display['replace_lines'])
            assert (root / display['svg_path']).is_file()


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp('revision-visuals')
    results = {}
    for campaign in ('M01', 'M02'):
        results[campaign] = press_visuals.build_revision_visuals(request(campaign), root / campaign, 'a' * 40)
    return root, results


def figure(built, campaign, number, data):
    root, results = built
    key = f'FRG-SOC-2028-{campaign}-Q{number:02}|{data}'
    display = results[campaign]['display'][key]
    svg = ET.parse(root / campaign / display['svg_path']).getroot()
    artifact = next(a for a in results[campaign]['artifacts'] if a['item_id'] + '|' + a['data_id'] == key)
    spec = json.loads((root / campaign / artifact['figure_spec_path']).read_text(encoding='utf-8'))
    return svg, spec, display


def test_revised_m01_does_not_restore_removed_land_use_or_visit_statistics(built):
    land, _, _ = figure(built, 'M01', 12, 'LAND-A')
    assert '[나]' in ''.join(land.itertext())
    assert '공장' not in ''.join(land.itertext())
    street, spec, _ = figure(built, 'M01', 14, 'STREET-A')
    assert spec['core_variables']['table_rows'][-1] == ['외곽 정', '50', '50']
    assert '방문' not in ''.join(street.itertext())
    culture, _, _ = figure(built, 'M01', 8, 'CULTURE-A')
    n = culture.find('.//s:text[@data-node="north"]', NS)
    s = culture.find('.//s:text[@data-node="south"]', NS)
    assert float(n.attrib['y']) < float(s.attrib['y'])
    assert '항로가 아님' in ''.join(culture.itertext())


def test_m02_watershed_keeps_two_separate_tributaries_to_r(built):
    svg, spec, display = figure(built, 'M02', 2, 'MAP-A')
    nodes = {n.attrib['data-node']: n.attrib for n in svg.findall('.//s:text[@data-node]', NS)}
    assert float(nodes['P']['x']) < float(nodes['Q']['x'])
    assert float(nodes['P']['y']) < float(nodes['R']['y'])
    assert spec['core_variables']['topology']['edges'] == [['산지 밭', 'P'], ['주택지', 'Q'], ['P', 'R'], ['Q', 'R']]
    assert display['replace_lines'] == []
    assert display['insert_before_line'] == spec['insert_before_line']
    assert '상류' not in ''.join(svg.itertext())


def test_m02_climate_graph_retains_raw_values_and_calendar_order(built):
    svg, spec, display = figure(built, 'M02', 5, 'DATA-A')
    assert spec['core_variables']['topology']['periods'] == ['1~3월', '4~6월', '7~9월', '10~12월']
    assert spec['core_variables']['topology']['series'] == [
        {'label': 'P 기온', 'values': [10, 18, 27, 19]},
        {'label': 'P 강수량', 'values': [240, 100, 30, 150]},
        {'label': 'Q 기온', 'values': [26, 18, 11, 19]},
        {'label': 'Q 강수량', 'values': [40, 140, 260, 100]},
    ]
    assert len(svg.findall('.//s:rect[@data-climate-value]', NS)) == 16
    assert display['replace_lines']
    assert not any(word in ''.join(svg.itertext()) for word in ('저장량', '부족량', '여름', '겨울', '충족'))


def test_m02_network_preserves_only_four_undirected_weighted_edges(built):
    svg, spec, _ = figure(built, 'M02', 20, 'MAP-A')
    assert spec['core_variables']['topology']['edges'] == [
        ['A', 'B', 8], ['A', 'C', 7], ['A', 'D', 5], ['B', 'C', 30]
    ]
    assert len(svg.findall('.//s:line[@data-edge]', NS)) == 4
    assert not any(word in ''.join(svg.itertext()) for word in ('순위', '1위', '중심', '최대', '합계'))


def test_raster_network_node_background_clears_edges_like_svg(built):
    root, results = built
    display = results['M02']['display']['FRG-SOC-2028-M02-Q20|MAP-A']
    with Image.open(root / 'M02' / display['png_path']) as png:
        assert png.getpixel((805, 140)) == 255


def test_service_map_keeps_one_node_per_place_and_four_paths(built):
    svg, spec, _ = figure(built, 'M02', 13, 'MAP-A')
    nodes = svg.findall('.//s:text[@data-node]', NS)
    assert len(nodes) == 4
    assert spec['core_variables']['topology']['edges'] == [['W', '서관', 5], ['W', '동관', 35], ['E', '서관', 35], ['E', '동관', 5]]


def test_revision_builder_rejects_stale_content_and_unknown_requests(tmp_path):
    source = request('M02')
    stale = copy.deepcopy(source)
    stale['requests'][0]['source_content'] += '변조'
    with pytest.raises(press_visuals.VisualBuildError, match='SOURCE_CONTENT_SHA256'):
        press_visuals.build_revision_visuals(stale, tmp_path, 'a' * 40)
    source['requests'][0]['data_id'] = '../outside'
    with pytest.raises(press_visuals.VisualBuildError, match='UNSUPPORTED_VISUAL_REQUEST'):
        press_visuals.build_revision_visuals(source, tmp_path, 'a' * 40)
