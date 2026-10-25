import json
import pytest
import httpx
from research.clients import TavilySearch, ResearchError
from tests.fakes import FixtureSearch, FixtureAnalyst, SNAPSHOT, DATA, source, claim
from research.graph import build_graph
from research.models import Request, Synthesis, Briefing
from research.quality import audit_findings
from research.runner import run_research


def test_live_completion_persists_and_loads_without_keys(tmp_path, monkeypatch):
    import research.runner as runner
    from research.storage import list_saved_searches, load_saved_search
    monkeypatch.setattr(runner, 'TavilySearch', lambda key: FixtureSearch())
    monkeypatch.setattr(runner, 'Analyst', lambda key, model: FixtureAnalyst())
    req = Request(competitor_names=['Asana', 'monday.com', 'ClickUp'], company='Notion')
    result = run_research(req, tavily_key='test-search-key', openrouter_key='test-model-key', runs_dir=tmp_path)
    assert len(result['competitors']) == 3
    assert result['mode'] == 'live'
    assert len(list_saved_searches(tmp_path)) == 1
    assert load_saved_search(result['run_id'], tmp_path) == result
    assert not list(tmp_path.glob('*/checkpoints.sqlite'))
    for path in tmp_path.glob('*/*'):
        assert 'test-search-key' not in path.read_text()
        assert 'test-model-key' not in path.read_text()
    Briefing.model_validate(result)


def test_evidence_gate_rejects_hallucinated_and_stale_news():
    src = source(DATA[0], 'news')
    findings = dict(features=[claim('Unsupported capability', 'invented-id')], positioning=[],
        news=[dict(headline=claim('Old announcement', src['id']), published_on='2020-01-01'),
              dict(headline=claim('Future announcement', src['id']), published_on='2030-01-01'),
              dict(headline=claim('Undated announcement', src['id']), published_on='unknown')], gaps=[])
    out = audit_findings(findings, [src], 30, SNAPSHOT)
    assert out['features'] == []
    assert out['news'] == []
    assert any('unsupported' in g for g in out['gaps'])


def test_search_failure_is_partial_and_followup_is_bounded():
    class BrokenSearch(FixtureSearch):
        calls = 0
        def search(self, query, category, **kwargs):
            self.calls += 1
            if category == 'product':
                raise ResearchError('Unavailable')
            return super().search(query, category, **kwargs)
    class MissingFeatures(FixtureAnalyst):
        def ask(self, schema, task, data):
            out = super().ask(schema, task, data)
            if 'features' in out:
                out['features'] = []
            return out
    search = BrokenSearch()
    result = build_graph(search, MissingFeatures()).invoke(dict(request=Request(competitor_names=['Asana', 'monday.com', 'ClickUp'], company='Notion').model_dump(),
                                                           as_of=SNAPSHOT, reports=[], events=[]))
    assert len(result['reports']) == 3
    assert search.calls == 12  # Three identity searches + six initial searches + three targeted feature retries.
    assert all(r['errors'] and not r['findings']['features'] for r in result['reports'])


def test_failed_live_search_leaves_no_saved_files(tmp_path, monkeypatch):
    import research.runner as runner
    class FailingAnalyst(FixtureAnalyst):
        def ask(self, schema, task, data):
            if schema is Synthesis:
                raise ResearchError('Temporary model failure')
            return super().ask(schema, task, data)
    monkeypatch.setattr(runner, 'TavilySearch', lambda key: FixtureSearch())
    monkeypatch.setattr(runner, 'Analyst', lambda key, model: FailingAnalyst())
    with pytest.raises(ResearchError):
        run_research(Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp']),
                     tavily_key='test-key', openrouter_key='test-key', runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_tavily_request_contract_and_safe_auth_error(monkeypatch):
    requests = []
    def post(self, url, **kwargs):
        requests.append(kwargs)
        return httpx.Response(200, json={'results': [
            {'title': 'News', 'url': 'https://example.com/news', 'content': 'announcement', 'published_date': '2026-10-22'},
            {'title': 'Unsafe URL', 'url': 'javascript:alert(1)', 'content': 'ignore'}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    client = TavilySearch('secret-value')
    results = client.search('Company latest', 'news', days=14)
    assert len(results) == 1
    assert requests[0]['json']['topic'] == 'news'
    assert 'start_date' in requests[0]['json']
    assert 'secret-value' not in json.dumps(results)
    client.search('Company features', 'product', domain='example.com')
    assert requests[1]['json']['include_domains'] == ['example.com']
    def rejected(self, url, **kwargs):
        return httpx.Response(401, text='secret-value')
    monkeypatch.setattr(httpx.Client, 'post', rejected)
    with pytest.raises(ResearchError, match='rejected') as exc:
        client.search('query', 'product')
    assert 'secret-value' not in str(exc.value)


def test_run_id_and_live_only_validation(tmp_path):
    req = Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp'])
    with pytest.raises(ValueError):
        run_research(req, run_id='../unsafe', tavily_key='test-key', openrouter_key='test-key', runs_dir=tmp_path)
    with pytest.raises(ValueError, match='Only live'):
        run_research(req, mode='demo', runs_dir=tmp_path)
    with pytest.raises(ResearchError, match='Configure'):
        run_research(req, runs_dir=tmp_path)


def test_publication_date_handles_tavily_rfc_dates():
    from research.clients import publication_date
    assert publication_date('Thu, 22 Oct 2026 09:30:00 GMT') == '2026-10-22'
    assert publication_date('2026-10-22T09:30:00Z') == '2026-10-22'
    assert publication_date('unknown') is None


def test_temporary_search_errors_retry_three_times(monkeypatch):
    from tenacity import wait_none
    calls = []
    def fail(self, url, **kwargs):
        calls.append(url)
        return httpx.Response(429)
    monkeypatch.setattr(httpx.Client, 'post', fail)
    monkeypatch.setattr(TavilySearch._post.retry, 'wait', wait_none())
    with pytest.raises(ResearchError, match='three attempts'):
        TavilySearch('secret').search('query', 'news')
    assert len(calls) == 3


@pytest.mark.parametrize('names', [[], ['One', 'Two'], ['One', 'Two', 'Three', 'Four'],
                                    ['', 'Two', 'Three'], ['One', ' one ', 'Three'], ['Notion', 'Two', 'Three']])
def test_competitor_input_validation(names):
    with pytest.raises(ValueError):
        Request(company='Notion', competitor_names=names)


def test_custom_competitors_reach_research_in_supplied_order():
    from research.models import Discovery, Findings
    from research.clients import source_id
    names = ['Miro', 'Figma', 'Mural']
    queries = []
    class Search:
        def search(self, query, category, **kwargs):
            queries.append(query)
            return [dict(id=source_id('https://example.com/' + name.lower()), title=name,
                         url='https://example.com/' + name.lower(), content=name,
                         category=category, retrieved_at=SNAPSHOT, published_at=None)
                    for name in names]
    class Model:
        def ask(self, schema, task, data):
            if schema is Discovery:
                return {'competitors': [dict(name=name, domain=name.lower() + '.com',
                    rationale='User-supplied research scope', source_ids=[source_id('https://example.com/' + name.lower())])
                    for name in reversed(names)]}
            if schema is Findings:
                return dict(features=[], positioning=[], news=[], gaps=['No supported data'])
            return dict(executive_summary=[], opportunities=[], watchlist=[])
    result = build_graph(Search(), Model()).invoke(dict(request=Request(company='Notion', competitor_names=names).model_dump(),
                                                       as_of=SNAPSHOT, reports=[], events=[]))
    assert [c['name'] for c in result['competitors']] == names
    assert {r['competitor']['name'] for r in result['reports']} == set(names)
    assert all(any(query.startswith(name) and 'core features' in query for query in queries) for name in names)
    assert not any('Asana' in query or 'ClickUp' in query for query in queries)


def test_identity_agent_cannot_substitute_user_competitors():
    request = Request(company='Notion', competitor_names=['Miro', 'Figma', 'Mural'])
    with pytest.raises(ResearchError, match='supplied competitors'):
        build_graph(FixtureSearch(), FixtureAnalyst()).invoke(dict(request=request.model_dump(), as_of=SNAPSHOT, reports=[], events=[]))


def test_competitor_websites_are_optional_and_validate_http_urls():
    names = ['Miro', 'Figma', 'Mural']
    request = Request(company='Notion', competitor_names=names,
                      competitor_urls=[' https://www.miro.com/product ', '', None])
    assert request.competitor_urls == ['https://www.miro.com/product', None, None]
    assert Request(company='Notion', competitor_names=names).competitor_urls == [None] * 3
    for urls in [['javascript:alert(1)', '', ''], ['not-a-url', '', ''], ['https://user:password@example.com', '', '']]:
        with pytest.raises(ValueError):
            Request(company='Notion', competitor_names=names, competitor_urls=urls)


def test_supplied_websites_control_research_domains():
    class Search(FixtureSearch):
        calls = []
        def search(self, query, category, **kwargs):
            self.calls.append((category, kwargs.get('domain')))
            return super().search(query, category, **kwargs)
    search = Search()
    request = Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp'],
                      competitor_urls=['https://www.asana.example/products', None, None])
    result = build_graph(search, FixtureAnalyst()).invoke(dict(request=request.model_dump(), as_of=SNAPSHOT, reports=[], events=[]))
    assert result['competitors'][0]['domain'] == 'asana.example'
    assert ('discovery', 'asana.example') in search.calls
    assert ('product', 'asana.example') in search.calls


def test_analysis_routes_structured_output_to_openrouter(monkeypatch):
    import langchain_openai
    from research.clients import Analyst
    requests = []
    output = dict(executive_summary=[], opportunities=[], watchlist=[])
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            'id': 'test-completion', 'object': 'chat.completion', 'created': 0,
            'model': 'openai/gpt-4.1-mini',
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': json.dumps(output)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}})
    original = langchain_openai.ChatOpenAI
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kwargs: original(http_client=client, **kwargs))
        analyst = Analyst('test-openrouter-key', 'openai/gpt-4.1-mini')
        assert analyst.ask(Synthesis, 'Summarize the evidence', {}) == output
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == 'https://openrouter.ai/api/v1/chat/completions'
    assert request.headers['Authorization'] == 'Bearer test-openrouter-key'
    payload = json.loads(request.content)
    assert payload['model'] == 'openai/gpt-4.1-mini'
    assert payload['response_format']['type'] == 'json_schema'
    assert payload['response_format']['json_schema']['strict'] is True
    assert payload['provider']['require_parameters'] is True


def test_openrouter_provider_errors_are_sanitized(monkeypatch):
    import langchain_openai
    from research.clients import Analyst
    original = langchain_openai.ChatOpenAI
    def reject(request):
        return httpx.Response(401, json={'error': {'message': 'private-provider-detail', 'code': 401}})
    with httpx.Client(transport=httpx.MockTransport(reject)) as client:
        monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kwargs: original(http_client=client, **kwargs))
        analyst = Analyst('private-api-key', 'openai/gpt-4.1-mini')
        with pytest.raises(ResearchError, match='OpenRouter') as error:
            analyst.ask(Synthesis, 'Summarize', {})
        assert 'private-api-key' not in str(error.value)
        assert 'private-provider-detail' not in str(error.value)


def test_history_excludes_demos_drafts_and_corrupt_files(tmp_path):
    from research.storage import list_saved_searches, load_saved_search
    for index, content in enumerate(['not json', json.dumps({'mode': 'demo'}), json.dumps({'mode': 'live'})]):
        folder = tmp_path / f'{index:032x}'
        folder.mkdir()
        (folder / 'briefing.json').write_text(content)
    draft = tmp_path / ('f' * 32)
    draft.mkdir()
    (draft / 'metadata.json').write_text('{}')
    assert list_saved_searches(tmp_path) == []
    with pytest.raises(ValueError):
        load_saved_search('../unsafe', tmp_path)


def test_research_focuses_on_requested_features_without_pricing():
    calls = []
    class Search(FixtureSearch):
        def search(self, query, category, **kwargs):
            calls.append((query, category))
            return super().search(query, category, **kwargs)
    request = Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp'],
                      feature_focus='approval workflows and integrations')
    result = build_graph(Search(), FixtureAnalyst()).invoke(dict(request=request.model_dump(), as_of=SNAPSHOT, reports=[], events=[]))
    assert len(calls) == 9
    assert all('pricing' not in query.casefold() and category != 'pricing' for query, category in calls)
    assert all('approval workflows and integrations' in query for query, category in calls if category == 'product')
    assert all('pricing' not in report['findings'] for report in result['reports'])


def test_human_review_persists_only_for_completed_live_search(tmp_path, monkeypatch):
    import research.runner as runner
    from research.storage import save_review, load_review
    monkeypatch.setattr(runner, 'TavilySearch', lambda key: FixtureSearch())
    monkeypatch.setattr(runner, 'Analyst', lambda key, model: FixtureAnalyst())
    brief = run_research(Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp']),
                         tavily_key='test-key', openrouter_key='test-key', runs_dir=tmp_path)
    assert brief['duration_seconds'] >= 0
    assert load_review(brief['run_id'], tmp_path) is None
    review = save_review(brief['run_id'], dict(usable=True, total_task_minutes=7.5, notes='Sources checked'), tmp_path)
    assert load_review(brief['run_id'], tmp_path) == review
    with pytest.raises(FileNotFoundError):
        save_review('b' * 32, dict(usable=True, total_task_minutes=7.5), tmp_path)
    with pytest.raises(ValueError):
        save_review(brief['run_id'], dict(usable=True, total_task_minutes=-1), tmp_path)
