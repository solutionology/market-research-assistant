import json
import pytest
from research import prompts
from research.clients import ResearchError
from research.models import Request
from research.orchestrator import build_graph
from tests.fakes import FixtureAnalyst, FixtureSearch, SNAPSHOT


def test_agents_use_editable_prompt_files(tmp_path, monkeypatch):
    original = prompts.files('research.prompts')
    for filename in ['shared_system.md', 'identity.md', 'extraction.md', 'orchestrator.md', 'search_queries.json']:
        (tmp_path / filename).write_text(original.joinpath(filename).read_text())
    for filename in ['identity.md', 'extraction.md', 'orchestrator.md']:
        (tmp_path / filename).write_text('Custom instructions: ' + filename)
    monkeypatch.setattr(prompts, 'files', lambda package: tmp_path)
    tasks = []
    class Analyst(FixtureAnalyst):
        def ask(self, schema, task, data):
            tasks.append(task)
            return super().ask(schema, task, data)
    request = Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp'])
    result = build_graph(FixtureSearch(), Analyst()).invoke(dict(request=request.model_dump(), as_of=SNAPSHOT, reports=[], events=[]))
    assert len(result['reports']) == 3
    assert tasks.count('Custom instructions: identity.md') == 1
    assert tasks.count('Custom instructions: extraction.md') == 3
    assert tasks.count('Custom instructions: orchestrator.md') == 1
    (tmp_path / 'shared_system.md').write_text('First revision')
    assert prompts.load_prompt('shared_system.md') == 'First revision'
    (tmp_path / 'shared_system.md').write_text('Second revision')
    assert prompts.load_prompt('shared_system.md') == 'Second revision'


def test_query_configuration_and_clear_configuration_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, 'files', lambda package: tmp_path)
    (tmp_path / 'search_queries.json').write_text(json.dumps({'product': '{name} workflow capabilities'}))
    assert prompts.render_query('product', name='Acme') == 'Acme workflow capabilities'
    with pytest.raises(ResearchError, match='template'):
        prompts.render_query('product')
    with pytest.raises(ResearchError, match='Cannot read prompt'):
        prompts.load_prompt('missing.md')
    (tmp_path / 'empty.md').write_text('  ')
    with pytest.raises(ResearchError, match='empty'):
        prompts.load_prompt('empty.md')
