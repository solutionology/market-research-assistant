from research.clients import ResearchError
from research.evidence import unique_sources
from research.prompts import render_query


class ResearchAgent:
    def __init__(self, search):
        self.search = search

    def __call__(self, state):
        search = self.search
        c, req = state['competitor'], state['request']
        attempt = state.get('attempt', 0) + 1
        sources = list(state.get('sources', []))
        errors = list(state.get('errors', []))
        missing = []
        if attempt == 1 or not state.get('findings', {}).get('features') or not state.get('findings', {}).get('positioning'):
            missing.append(('product', render_query('product', name=c['name'], context=req['context'], feature_focus=req.get('feature_focus', ''), geography=req['geography']), c['domain']))
        if attempt == 1 or not state.get('findings', {}).get('news'):
            missing.append(('news', render_query('news', name=c['name'], domain=c['domain']), None))
        for category, query, domain in missing:
            try:
                sources.extend(search.search(query, category, domain=domain, days=req['news_days']))
            except ResearchError:
                errors.append(f'{c["name"]}: {category} search unavailable on pass {attempt}.')
        return {'sources': unique_sources(sources), 'errors': list(dict.fromkeys(errors)), 'attempt': attempt,
                'events': state.get('events', []) + [f"Research agent · {c['name']}: pass {attempt}, {len(missing)} searches."]}
