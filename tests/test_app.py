from pathlib import Path
from streamlit.testing.v1 import AppTest
from research.clients import ResearchError

APP = str(Path(__file__).resolve().parents[1] / 'streamlit_app.py')


def fill_form(app):
    next(w for w in app.text_input if w.label == 'Company').set_value('Notion')
    app.text_input(key='geography').set_value('Global')
    for i, name in enumerate(['Miro', 'Figma', 'Mural'], 1):
        app.text_input(key=f'competitor_{i}').set_value(name)


def test_starts_empty_and_never_renders_keys(tmp_path, monkeypatch):
    from research import storage
    monkeypatch.setattr(storage, 'DEFAULT_RUNS_DIR', tmp_path)
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    assert app.session_state['briefing'] is None
    assert not any('key' in w.label.casefold() for w in app.text_input)
    assert not app.metric
    app.selectbox(key='view').select('Saved searches').run()
    assert not app.exception
    assert any('No completed live searches' in e.value for e in app.info)


def test_blank_company_and_competitors_are_rejected():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.button[0].click().run()
    assert not app.exception
    assert any('Enter a company' in e.value for e in app.error)
    next(w for w in app.text_input if w.label == 'Company').set_value('Notion')
    app.text_input(key='geography').set_value('Global')
    app.button[0].click().run()
    assert not app.exception
    assert any('three competitor names' in e.value for e in app.error)


def test_custom_inputs_pass_to_live_pipeline(monkeypatch):
    import research.runner as runner
    captured = []
    def capture(request, **kwargs):
        captured.append((request, kwargs))
        raise ResearchError('Test failure')
    monkeypatch.setattr(runner, 'run_research', capture)
    app = AppTest.from_file(APP, default_timeout=30).run()
    fill_form(app)
    app.text_input(key='competitor_url_1').set_value('https://miro.com')
    app.button[0].click().run()
    assert not app.exception
    assert captured[0][0].competitor_names == ['Miro', 'Figma', 'Mural']
    assert captured[0][0].competitor_urls == ['https://miro.com/', None, None]
    assert app.session_state['briefing'] is None


def test_saved_history_is_available_in_new_app_session(tmp_path, monkeypatch):
    import research.runner as runner
    from research import storage
    from research.models import Request
    from tests.fakes import FixtureSearch, FixtureAnalyst
    monkeypatch.setattr(storage, 'DEFAULT_RUNS_DIR', tmp_path)
    monkeypatch.setattr(runner, 'TavilySearch', lambda key: FixtureSearch())
    monkeypatch.setattr(runner, 'Analyst', lambda key, model: FixtureAnalyst())
    brief = runner.run_research(Request(company='Notion', competitor_names=['Asana', 'monday.com', 'ClickUp']),
                                tavily_key='test-key', openrouter_key='test-key')
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.selectbox(key='view').select('Saved searches').run()
    assert not app.exception
    assert app.session_state['briefing']['run_id'] == brief['run_id']
    assert app.metric[0].value == '3'
    assert not any('key' in w.label.casefold() for w in app.text_input)


def test_selecting_new_research_clears_form_and_previous_results(tmp_path, monkeypatch):
    from research import storage
    monkeypatch.setattr(storage, 'DEFAULT_RUNS_DIR', tmp_path)
    app = AppTest.from_file(APP, default_timeout=30).run()
    fill_form(app)
    app.text_area(key='context').set_value('Product team workflows')
    app.text_input(key='feature_focus').set_value('Approvals')
    app.text_input(key='competitor_url_1').set_value('https://miro.com')
    app.slider(key='news_days').set_value(90)
    app.run()
    app.selectbox(key='view').select('Saved searches').run()
    # A previously viewed result must also be discarded on returning to the form.
    app.session_state['briefing'] = {'mode': 'live', 'run_id': 'previous-result'}
    app.selectbox(key='view').select('New research').run()
    assert not app.exception
    assert all(widget.value == '' for widget in app.text_input)
    assert all(widget.value == '' for widget in app.text_area)
    assert app.slider(key='news_days').value == 30
    assert app.session_state['briefing'] is None
    assert not app.metric
    assert not any('Competitive briefing' in header.value for header in app.header)
