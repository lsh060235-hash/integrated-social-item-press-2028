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
    if any('editorial_solution' in i for i in packet['items']):
        verify_solution_columns(packet, pdf)


def verify_solution_columns(packet, pdf):
    """Hancom's final-page balancing can split even a keep-with-next group."""
    import fitz
    from press_verify import normalized
    columns=[]
    with fitz.open(pdf) as doc:
        for pn,page in enumerate(doc,1):
            groups=[[],[]]
            for block in page.get_text('rawdict')['blocks']:
                for line in block.get('lines',[]):
                    text=''.join(c['c'] for s in line['spans'] for c in s['chars'])
                    x,y,_,_=line['bbox']
                    groups[int(x>page.rect.width/2-8)].append((y,x,text))
            for col,lines in enumerate(groups,1):
                columns.append((pn,col,normalized(''.join(t for _,_,t in sorted(lines)))))
    locations=[]
    for item in packet['items']:
        if 'editorial_solution' not in item: continue
        e=item['editorial_solution']
        head=normalized(f"{item['number']}. {e['topic']} 정답 {CIRCLED[e['answer']-1]}")
        found=[(pn,col,t) for pn,col,t in columns if head in t]
        if len(found)!=1: raise ContractError('SOLUTION_ITEM_HEADER_MISMATCH')
        pn,col,text=found[0]
        frame=text[text.index(head):]
        for other in packet['items']:
            if other['number']<=item['number'] or 'editorial_solution' not in other: continue
            nxt=other['editorial_solution']
            next_head=normalized(f"{other['number']}. {nxt['topic']} 정답 {CIRCLED[nxt['answer']-1]}")
            if next_head in frame: frame=frame[:frame.index(next_head)]
        expected=[*solution_units(item),'정답 해설','[오답피하기]']
        expected += [CIRCLED[w['choice']-1]+' '+w['text'] for w in e['wrong_answers']]
        if any(normalized(t) not in frame for t in expected):
            raise ContractError(f"SOLUTION_ITEM_SPLIT: {item['number']}")
        locations.append({'number':item['number'],'page':pn,'column':col})
    return locations
