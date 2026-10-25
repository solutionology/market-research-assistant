"""Synthetic test doubles. Never imported by the application."""
from research.clients import source_id
from research.models import Discovery, Findings, Synthesis
SNAPSHOT = '2026-10-25T12:00:00+00:00'
DATA = [dict(name=name, domain=domain, rationale='Synthetic relevance',
             features='Synthetic feature evidence', positioning='Synthetic positioning evidence',
             news='Synthetic announcement', news_url=f'https://{domain}/news', news_date='2026-10-22',
             gap='Synthetic evidence gap')
        for name, domain in [('Asana', 'asana.com'), ('monday.com', 'monday.com'), ('ClickUp', 'clickup.com')]]

def claim(text, sid, kind='fact'):
    return dict(text=text, source_ids=[sid], kind=kind, confidence='medium')


def source(row, category):
    url = row['news_url'] if category == 'news' else f"https://{row['domain']}/features"
    content = row['news'] if category == 'news' else ' '.join(row[k] for k in ('features', 'positioning'))
    return dict(id=source_id(url), title=f"{row['name']} {'news' if category == 'news' else 'product features'}",
                url=url, content=content, category=category, retrieved_at=SNAPSHOT,
                published_at=row['news_date'] if category == 'news' else None)


class FixtureSearch:
    def search(self, query, category, **kwargs):
        if category == 'discovery':
            return [source(row, 'discovery') for row in DATA]
        row = next(row for row in DATA if row['name'] in query)
        return [source(row, category)]


class FixtureAnalyst:
    def ask(self, schema, task, data):
        if schema is Discovery:
            return dict(competitors=[dict(name=r['name'], domain=r['domain'], rationale=r['rationale'],
                                        source_ids=[source(r, 'discovery')['id']]) for r in DATA])
        if schema is Findings:
            row = next(r for r in DATA if r['name'] == data['competitor']['name'])
            sid = source(row, 'product')['id']
            return dict(features=[claim(row['features'], sid)],
                        positioning=[claim(row['positioning'], sid)],
                        news=[dict(headline=claim(row['news'], source(row, 'news')['id']), published_on=row['news_date'])],
                        gaps=[row['gap'], 'Curated demonstration evidence; independent customer validation was not performed.'])
        if schema is Synthesis:
            a, m, c = (source(r, 'product')['id'] for r in DATA)
            return dict(executive_summary=[
                claim('The illustrative competitor set spans structured execution, configurable workflows and suite consolidation.', a, 'inference'),
                dict(text='Validate integration depth through workflow trials across all three vendors.',
                     source_ids=[a, m, c], kind='fact', confidence='high')],
                opportunities=[dict(text='For Notion’s project-workspace use case, test whether connecting knowledge directly to project execution improves buyer preference. Validate with win/loss interviews.',
                                    source_ids=[a, c], kind='inference', confidence='medium')],
                watchlist=[dict(text='Track AI workflow packaging, usage credits and launch adoption across the three vendors; announcements do not establish customer impact.',
                                source_ids=[source(r, 'news')['id'] for r in DATA], kind='inference', confidence='medium')])
        raise ValueError('Unsupported demo schema')
