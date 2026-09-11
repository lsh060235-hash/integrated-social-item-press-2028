import pytest

from press_visuals import VisualBuildError, _revision_topology


def test_network_contains_only_existing_undirected_connections():
    topology = _revision_topology('revision_resilient_network', [
        '현재 연결은 M—P, M—Q, P—R, Q—R, R—S이며, 양방향으로 전달한다.'
    ])
    edges = topology['edges']
    assert edges == [['M', 'P'], ['M', 'Q'], ['P', 'R'], ['Q', 'R'], ['R', 'S']]
    # The student must discover that R is a cut vertex, not see a solved route.
    remaining = [edge for edge in edges if 'R' not in edge]
    assert all('S' not in edge for edge in remaining)
    assert ['Q', 'S'] not in edges


def test_care_flows_preserve_residency_and_facility_destinations():
    topology = _revision_topology('revision_care_flows', [
        'P시설은 A시, Q시설은 B시에 있다. P 이용자는 A시 주민 7명·B시 주민 13명이고, '
        'Q 이용자는 A시 주민 5명·B시 주민 11명이다.'
    ])
    assert topology['facilities'] == {'P': 'A', 'Q': 'B'}
    assert topology['flows'] == [['A', 'P', 7], ['B', 'P', 13], ['A', 'Q', 5], ['B', 'Q', 11]]
    assert 'settlement' not in topology


def test_exchange_distinguishes_storage_from_makers():
    topology = _revision_topology('revision_exchange_map', [
        '서쪽의 한반도 구역 K ┃ 바다 ┃ 동쪽의 일본 열도 구역 J',
        'X의 제작 구역 J → 현재 보관 구역 J, Y의 제작 구역 J → 현재 보관 구역 K.'
    ])
    assert topology['routes'] == [['X', 'J', 'J'], ['Y', 'J', 'K']]
    assert 'nationality' not in topology


def test_river_does_not_invent_a_bridge_or_eastern_office():
    topology = _revision_topology('revision_river_access', [
        '서쪽 강변: 거주지 P·기존 신고소 ║ 하천 ║ 동쪽 강변: 거주지 Q'
    ])
    assert topology['west'] == ['P', '기존 신고소']
    assert topology['east'] == ['Q']
    assert topology['crossings'] == []


@pytest.mark.parametrize('mode', ['resilient_network', 'river_access', 'care_flows', 'exchange_map'])
def test_unreadable_material_is_rejected(mode):
    with pytest.raises(VisualBuildError, match='MAP_TOPOLOGY_UNREADABLE'):
        _revision_topology('revision_' + mode, ['새로운 자료'])


def test_drawn_care_arrows_keep_the_four_original_counts():
    from PIL import ImageFont
    from press_visuals import _revision_ops
    topology = {'facilities': {'P': 'A', 'Q': 'B'},
                'flows': [['A', 'P', 7], ['B', 'P', 13], ['A', 'Q', 5], ['B', 'Q', 11]]}
    _, ops = _revision_ops('revision_care_flows', topology, ImageFont.load_default())
    arrows = [op for op in ops if op[0] == 'line' and len(op) == 7 and 'data-flow' in op[6]]
    assert {a[6]['data-flow']: a[6]['data-count'] for a in arrows} == {
        'A-P': '7', 'B-P': '13', 'A-Q': '5', 'B-Q': '11'}
    assert arrows[1][1] > arrows[1][3]  # B residents travel to P in A.
    assert arrows[2][1] < arrows[2][3]  # A residents travel to Q in B.


def test_special_modes_cannot_be_used_for_unregistered_source():
    import hashlib
    from press_visuals import compile_visual_plan
    content = '현재 연결은 M—P, M—Q, P—R, Q—R, R—S이며, 양방향으로 전달한다.'
    digest = hashlib.sha256(content.encode()).hexdigest()
    request = {'requests': [{'item_id': 'test', 'data_id': 'map',
                            'source_content': content, 'source_content_sha256': digest}]}
    plan = {'schema_version': 'press-visual-plan-v1', 'figures': [{
        'item_id': 'test', 'data_id': 'map', 'source_content_sha256': digest,
        'mode': 'revision_resilient_network', 'lines': [content], 'replace': False}]}
    with pytest.raises(VisualBuildError, match='VISUAL_PLAN_REQUIRES_AUDITED_SOURCE'):
        compile_visual_plan(request, plan)
