"""Explicit, source-bound editorial prose; original teacher evidence stays intact."""
from copy import deepcopy
import re

from press_contract import ContractError

CIRCLED = '①②③④⑤'


def apply_editorial(packet, overlay):
    if (overlay.get('schema_version') != 'press-solutions-editorial-v0.1'
        or overlay.get('campaign_id') != packet['campaign_id']
        or overlay.get('source_version') != packet['source_version']
        or overlay.get('source_items_sha256') != packet['binding']['canonical_artifacts']['items_sha256']):
        raise ContractError('SOLUTION_SOURCE_MISMATCH')
    entries = overlay.get('items', [])
    if [e.get('number') for e in entries] != [i['number'] for i in packet['items']]:
        raise ContractError('SOLUTION_ITEM_COVERAGE')
    result = deepcopy(packet)
    for item, entry in zip(result['items'], entries, strict=True):
        answer = item['teacher']['answer']
        if (type(entry.get('answer')) is not int or entry['answer'] != answer
            or entry.get('source_item_sha256') != item['source_item_sha256']):
            raise ContractError('SOLUTION_ANSWER_OR_ITEM_MISMATCH')
        wrong = entry.get('wrong_answers', [])
        if ([w.get('choice') for w in wrong] != [n for n in range(1, 6) if n != answer]
            or any(type(w.get('choice')) is not int for w in wrong)):
            raise ContractError('SOLUTION_WRONG_ANSWER_COVERAGE')
        explanation = entry.get('explanation')
        if not isinstance(explanation, list) or not explanation:
            raise ContractError('SOLUTION_EXPLANATION_REQUIRED')
        texts = [entry.get('topic')] + explanation + [w.get('text') for w in wrong]
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ContractError('SOLUTION_EMPTY_TEXT')
        if any(re.search(r'\b[A-Z][A-Z0-9]*_[A-Z_0-9]+\b|\[[A-Z][A-Z0-9_-]*\]', t) for t in texts):
            raise ContractError('SOLUTION_INTERNAL_CODE')
        item['editorial_solution'] = deepcopy(entry)
    return result


def solution_units(item):
    """The exact prose to verify in both freshly rendered and sealed PDFs."""
    if 'editorial_solution' in item:
        e = item['editorial_solution']
        return [e['topic'], *e['explanation'], *[w['text'] for w in e['wrong_answers']]]
    t = item['teacher']
    return [t['rationale'], *[s['operation'] for s in t.get('solution_steps', [])],
            *[e['refutation'] for e in t.get('choice_evaluations', []) if e.get('refutation')]]


def verify_solutions(packet, pdf):
    import fitz
    from press_verify import missing_units
    with fitz.open(pdf) as doc:
        text = '\n'.join(p.get_text() for p in doc)
    units = [u for item in packet['items'] for u in solution_units(item)]
    if missing_units(units, text):
        raise ContractError('SOLUTION_TEXT_MISSING')
