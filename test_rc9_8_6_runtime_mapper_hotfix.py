from pathlib import Path
import ast

APP = Path(__file__).with_name('app.py')


def _function_source(name: str) -> str:
    text = APP.read_text(encoding='utf-8')
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return '\n'.join(lines[node.lineno-1:node.end_lineno])
    raise AssertionError(f'function {name} not found')


def test_condition_mapper_has_no_entry_candidate_scope_leak():
    src = _function_source('_mapear_condiciones_activas')
    assert "candidate.get('type')" not in src
    assert 'for other in all_candidates' not in src
    assert 'confluence_score = min(' not in src


def test_entry_committee_confluence_still_exists_in_entry_selector():
    src = _function_source('_select_optimal_entry')
    assert 'CONFLUENCIA ENTRE FAMILIAS INDEPENDIENTES' in src
    assert "candidate['_independent_family_count']" in src
    assert 'entry_candidate_adjustment' in src
