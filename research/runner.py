from __future__ import annotations

import json
import re
import tempfile
import uuid
from time import perf_counter
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from research.clients import Analyst, TavilySearch, ResearchError, utcnow
from research.formatting import briefing_markdown
from research.orchestrator import build_graph
from research.evidence import unique_sources
from research.models import Briefing, Request
from research import storage

ROOT = Path(__file__).resolve().parents[1]


def run_research(request: Request, *, mode='live', tavily_key='', openrouter_key='',
                 model='openai/gpt-4.1-mini', run_id=None, on_event=None, runs_dir=None):
    if mode != 'live':
        raise ValueError('Only live research is supported.')
    if not tavily_key or not openrouter_key:
        raise ResearchError('Configure TAVILY_API_KEY and OPENROUTER_API_KEY in .env or Streamlit secrets before running research.')
    run_id = run_id or uuid.uuid4().hex
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid run ID.')
    root = Path(runs_dir or storage.DEFAULT_RUNS_DIR)
    folder = root / run_id
    if folder.exists():
        raise ResearchError('This saved-search ID already exists. Start a new search.')
    started = perf_counter()
    as_of = utcnow()
    graph = build_graph(TavilySearch(tavily_key), Analyst(openrouter_key, model), InMemorySaver())
    config = {'configurable': {'thread_id': run_id}, 'max_concurrency': 3, 'recursion_limit': 30}
    inputs = dict(request=request.model_dump(), as_of=as_of, reports=[], events=[])
    for update in graph.stream(inputs, config, stream_mode='updates'):
        for name, value in update.items():
            if on_event:
                for event in value.get('events', [f'{name}: complete']):
                    on_event(event)
    state = graph.get_state(config).values
    reports = state['collated_reports']
    sources = unique_sources(state['discovery_sources'] + [s for r in reports for s in r['sources']])
    brief = Briefing(run_id=run_id, generated_at=utcnow(), duration_seconds=round(perf_counter() - started, 2), mode='live', request=request,
        competitors=reports, synthesis=state['synthesis'], sources=sources,
        events=state['events'], warnings=[
            'Competitors were supplied by the user; inclusion does not establish market rank or competitive relevance.',
            'Source-ID and date validation checks provenance structure, not whether every claim is true. Review sources before decisions.',
            'Search results may omit relevant information; vendor claims and announcements are not independent validation.',
            'Feature coverage reflects available evidence, not an exhaustive product evaluation.'
        ])
    output = brief.model_dump(mode='json')
    # Publish the two exports together, only after every graph stage has completed.
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.completed-', dir=root) as temp:
        staging = Path(temp) / run_id
        staging.mkdir()
        (staging / 'briefing.json').write_text(json.dumps(output, indent=2, ensure_ascii=False))
        (staging / 'briefing.md').write_text(briefing_markdown(output))
        staging.rename(folder)
    return output
