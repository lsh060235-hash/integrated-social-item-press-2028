import copy
import json
import subprocess
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from PIL import Image, ImageDraw, ImageFont

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


def test_m01_flood_panels_preserve_common_two_by_three_spatial_cells(built):
    svg, spec, _ = figure(built, 'M01', 5, 'FLOOD-A')
    cells = svg.findall('.//s:rect[@data-flood-cell]', NS)
    assert len(cells) == 12
    assert spec['core_variables']['topology']['panels'] == [
        {'label': '주거 인원(명)', 'rows': [['A: 10', 'B: 10', 'C: 10'], ['D: 20', 'E: 70', 'F: 200']]},
        {'label': '침수 범위', 'rows': [['A: 내부', 'B: 내부', 'C: 내부'], ['D: 내부', 'E: 경계', 'F: 외부']]},
    ]
    for panel in ('0', '1'):
        selected = [c for c in cells if c.attrib['data-panel'] == panel]
        assert len({c.attrib['y'] for c in selected}) == 2
        assert len({c.attrib['x'] for c in selected}) == 3


def test_m01_record_card_svg_and_raster_spec_use_same_serif_font(built):
    svg, spec, _ = figure(built, 'M01', 3, 'DIARY-A')
    assert svg.find('s:g', NS).attrib['font-family'].split(',')[0] == spec['font_family'] == 'Batang'


def test_flood_grid_panels_do_not_overlap_or_cover_third_column_glyphs(built):
    svg, _, display = figure(built, 'M01', 5, 'FLOOD-A')
    panels = [[cell for cell in svg.findall('.//s:rect[@data-flood-cell]', NS) if cell.attrib['data-panel'] == str(index)] for index in (0, 1)]
    assert max(float(c.attrib['x']) + float(c.attrib['width']) for c in panels[0]) < min(float(c.attrib['x']) for c in panels[1])
    assert all(0 <= float(c.attrib['x']) < float(c.attrib['x']) + float(c.attrib['width']) <= float(svg.attrib['viewBox'].split()[2]) for panel in panels for c in panel)
    font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 42)
    root, _ = built
    with Image.open(root / 'M01' / display['png_path']) as png:
        for label in ('C: 10', 'F: 200'):
            text = next(t for t in svg.findall('.//s:text', NS) if t.text == label)
            x, y = float(text.attrib['x']), float(text.attrib['y'])
            mask = Image.new('L', png.size, 255)
            ImageDraw.Draw(mask).text((x, y), label, font=font, fill=0)
            pixels = [(px, py) for py in range(int(y), int(y) + 60) for px in range(int(x), int(x) + 160) if mask.getpixel((px, py)) < 64]
            assert len(pixels) > 300
            assert sum(png.getpixel(point) < 128 for point in pixels) / len(pixels) > .99


@pytest.mark.parametrize('number,data,unit', [(13, 'WORK-A', '(kWh/주)'), (19, 'INDEX-B', '(지수)')])
def test_chart_unit_glyph_bounds_do_not_intersect_tick_labels(built, number, data, unit):
    svg, _, _ = figure(built, 'M01', number, data)
    font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 42)
    def bounds(text):
        x, y = float(text.attrib['x']), float(text.attrib['y'])
        a, b, c, d = font.getbbox(text.text)
        return x + a, y + b, x + c, y + d
    unit_bounds = bounds(next(t for t in svg.findall('.//s:text', NS) if t.text == unit))
    for tick in svg.findall('.//s:text[@data-axis-tick]', NS):
        b = bounds(tick)
        assert unit_bounds[2] <= b[0] or b[2] <= unit_bounds[0] or unit_bounds[3] <= b[1] or b[3] <= unit_bounds[1]


def test_m02_climate_calendar_labels_stay_on_one_line_with_month_unit(built):
    svg, _, _ = figure(built, 'M02', 5, 'DATA-A')
    for period in ('1~3월', '4~6월', '7~9월', '10~12월'):
        assert sum(t.text == period for t in svg.findall('.//s:text', NS)) == 4
    font = ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 42)
    rows = {}
    for t in svg.findall('.//s:text', NS):
        if t.text in ('1~3월', '4~6월', '7~9월', '10~12월'):
            rows.setdefault(t.attrib['y'], []).append((float(t.attrib['x']), font.getlength(t.text)))
    for row in rows.values():
        row.sort()
        assert all(left + width + 16 <= right for (left, width), (right, _) in zip(row, row[1:]))


def test_m01_container_flow_branches_without_calculated_counts(built):
    svg, spec, _ = figure(built, 'M01', 7, 'FLOW-A')
    assert len(svg.findall('.//s:line[@data-flow-edge]', NS)) == 4
    assert spec['core_variables']['topology']['fractions'] == ['출고량의 3/4', '나머지', '회수량의 1/2', '나머지']
    assert not any(value in ''.join(svg.itertext()) for value in ('180', '90', '60', '150', '37.5'))


@pytest.mark.parametrize('number,data,count', [(13, 'WORK-A', 9), (19, 'INDEX-B', 4)])
def test_m01_statistical_charts_have_shared_zero_axis_and_source_segments(built, number, data, count):
    svg, spec, _ = figure(built, 'M01', number, data)
    assert len(svg.findall('.//s:line[@data-zero-axis]', NS)) == 1
    assert len(svg.findall('.//s:text[@data-bar-label]', NS)) == count
    ticks = svg.findall('.//s:text[@data-axis-tick]', NS)
    assert [t.text for t in ticks] == ['0', '20', '40', '60', '80', '100', '120']
    segments = svg.findall('.//s:rect[@data-segment]', NS)
    assert len(segments) == (48 if number == 13 else 39)


def test_m01_shift_timeline_keeps_exact_boundaries_without_legal_classification(built):
    svg, spec, _ = figure(built, 'M01', 16, 'SHIFT-A')
    intervals = spec['core_variables'].get('topology', {}).get('intervals')
    assert intervals == [['09:00', '12:00'], ['12:00', '12:30'], ['12:30', '14:00'], ['14:00', '14:30'], ['14:30', '15:30'], ['15:30', '15:45']]
    bars = svg.findall('.//s:rect[@data-time-interval]', NS)
    assert len(bars) == 6
    assert float(bars[0].attrib['width']) / float(bars[-1].attrib['width']) == pytest.approx(12, rel=.001)
    assert not any(value in ''.join(svg.itertext()) for value in ('총 근로', '법정', '위반', '분 합계'))
