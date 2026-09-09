import copy
import hashlib
import json

import pytest

import press_revision
import press_verify
from press_revision import (
    apply_student_editorial,
    augment_student_table_visuals,
    validate_student_editorial_visuals,
)


def packet():
    content = "출제자가 구성한 가상 자료이다.\n| 항목 | 값 |\n| A | 1 |"
    return {
        "campaign_id": "FRG-SOC-2028-M01",
        "source_version": "v1",
        "binding": {"canonical_artifacts": {"items_sha256": "a" * 64}},
        "items": [
            {
                "item_id": "FRG-SOC-2028-M01-Q01",
                "student_view": {
                    "prompt": "옳은 것은?",
                    "choices": ["1", "2", "3", "4", "5"],
                    "conditions": [{"condition_id": "DATA-A", "content": content}],
                },
            }
        ],
    }


def overlay(source):
    before = source["items"][0]["student_view"]["conditions"][0]["content"]
    return {
        "schema_version": "press-student-editorial-v0.1",
        "campaign_id": source["campaign_id"],
        "source_version": source["source_version"],
        "source_items_sha256": source["binding"]["canonical_artifacts"]["items_sha256"],
        "conditions": [
            {
                "item_id": source["items"][0]["item_id"],
                "condition_id": "DATA-A",
                "source_content_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "content": "다음은 가상 자료이다.\n| 항목 | 값 |\n| A | 1 |",
            }
        ],
    }


def test_student_editorial_changes_only_bound_condition_copy():
    source = packet()
    original = copy.deepcopy(source)

    edited = apply_student_editorial(source, overlay(source))

    assert source == original
    assert edited["items"][0]["student_view"]["prompt"] == "옳은 것은?"
    assert edited["items"][0]["student_view"]["choices"] == ["1", "2", "3", "4", "5"]
    assert edited["items"][0]["student_view"]["conditions"][0]["content"].startswith("다음은")


def test_student_editorial_keeps_bound_visual_lines_buildable():
    source = packet()
    edited = apply_student_editorial(source, overlay(source))
    plan = {
        "figures": [
            {
                "item_id": source["items"][0]["item_id"],
                "data_id": "DATA-A",
                "lines": ["| 항목 | 값 |", "| A | 1 |"],
            }
        ]
    }

    validate_student_editorial_visuals(edited, plan)


def test_student_editorial_rejects_change_to_bound_visual_line():
    source = packet()
    changed = overlay(source)
    changed["conditions"][0]["content"] = "다음은 가상 자료이다.\n| 항목 | 수치 |\n| A | 1 |"
    edited = apply_student_editorial(source, changed)
    plan = {
        "figures": [
            {
                "item_id": source["items"][0]["item_id"],
                "data_id": "DATA-A",
                "lines": ["| 항목 | 값 |", "| A | 1 |"],
            }
        ]
    }

    with pytest.raises(ValueError, match="STUDENT_EDITORIAL_VISUAL_SOURCE_CHANGED"):
        validate_student_editorial_visuals(edited, plan)


def test_student_editorial_adds_source_bound_table_visuals_without_mutating_source():
    source = packet()
    source['visual_handoff'] = {
        'schema_version': 'integrated-social-visual-handoff-v1',
        'requests': [],
    }
    edited = apply_student_editorial(source, overlay(source))
    plan = {'schema_version': 'press-visual-plan-v1', 'figures': []}
    original_source = copy.deepcopy(source)
    original_plan = copy.deepcopy(plan)

    request, render_plan = augment_student_table_visuals(source, edited, plan)

    assert source == original_source
    assert plan == original_plan
    assert len(request['requests']) == len(render_plan['figures']) == 1
    entry = request['requests'][0]
    figure = render_plan['figures'][0]
    assert entry['source_content'] == edited['items'][0]['student_view']['conditions'][0]['content']
    assert entry['source_content_sha256'] == hashlib.sha256(entry['source_content'].encode()).hexdigest()
    assert figure['mode'] == 'table' and figure['replace'] is True
    assert figure['lines'] == ['| 항목 | 값 |', '| A | 1 |']


def test_student_editorial_reuses_existing_generic_table_visual_as_replacement():
    source = packet()
    condition = source['items'][0]['student_view']['conditions'][0]
    source['visual_handoff'] = {'requests': [{
        'item_id': source['items'][0]['item_id'],
        'data_id': condition['condition_id'],
    }]}
    plan = {'figures': [{
        'item_id': source['items'][0]['item_id'],
        'data_id': condition['condition_id'],
        'mode': 'table',
        'replace': False,
    }]}

    request, render_plan = augment_student_table_visuals(source, source, plan)

    assert len(request['requests']) == 1
    assert len(render_plan['figures']) == 1
    assert render_plan['figures'][0]['replace'] is True
    assert plan['figures'][0]['replace'] is False


def test_student_editorial_recognizes_table_rows_without_outer_pipes():
    source = packet()
    condition = source['items'][0]['student_view']['conditions'][0]
    condition['content'] = '가상 자료이다.\n항목 | 값\n--- | ---\nA | 1'
    source['visual_handoff'] = {
        'schema_version': 'integrated-social-visual-handoff-v1',
        'requests': [],
    }
    plan = {'schema_version': 'press-visual-plan-v1', 'figures': []}

    request, render_plan = augment_student_table_visuals(source, source, plan)

    assert len(request['requests']) == 1
    assert render_plan['figures'][0]['lines'] == ['항목 | 값', '--- | ---', 'A | 1']


@pytest.mark.parametrize("field", ["campaign_id", "source_version", "source_items_sha256"])
def test_student_editorial_rejects_wrong_source_identity(field):
    source = packet()
    changed = overlay(source)
    changed[field] = "wrong"

    with pytest.raises(ValueError, match="STUDENT_EDITORIAL_SOURCE_MISMATCH"):
        apply_student_editorial(source, changed)


def test_student_editorial_rejects_stale_or_duplicate_condition():
    source = packet()
    changed = overlay(source)
    changed["conditions"][0]["source_content_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="STUDENT_EDITORIAL_CONTENT_MISMATCH"):
        apply_student_editorial(source, changed)

    changed = overlay(source)
    changed["conditions"].append(dict(changed["conditions"][0]))
    with pytest.raises(ValueError, match="STUDENT_EDITORIAL_DUPLICATE"):
        apply_student_editorial(source, changed)


def test_seal_rejects_student_editorial_changed_after_build(tmp_path):
    plan = tmp_path / "visual-plan.json"
    plan.write_text("{}", encoding="utf-8")
    runtime = tmp_path / "runtime.json"
    runtime.write_text("{}", encoding="utf-8")
    editorial = tmp_path / "student-editorial.json"
    editorial.write_text("{}", encoding="utf-8")
    verification = {
        "visual_plan_sha256": press_verify.sha(plan),
        "student_editorial_sha256": press_verify.sha(editorial),
        "reproduction_files": press_verify.make_file_binding(tmp_path, [runtime]),
    }
    (tmp_path / "verification.json").write_text(json.dumps(verification), encoding="utf-8")
    press_revision.verify_saved_plan(tmp_path)

    editorial.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="STUDENT_EDITORIAL_CHANGED_AFTER_BUILD"):
        press_revision.verify_saved_plan(tmp_path)
