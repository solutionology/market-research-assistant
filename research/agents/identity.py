import re
from urllib.parse import urlsplit
from research.clients import ResearchError
from research.models import Discovery
from research.evidence import unique_sources
from research.prompts import load_prompt, render_query


class IdentityAgent:
    def __init__(self, search, analyst):
        self.search = search
        self.analyst = analyst

    def __call__(self, state):
        search = self.search
        analyst = self.analyst
        req = state['request']
        names = req['competitor_names']
        urls = req.get('competitor_urls', [None, None, None])
        supplied_domains = {name.casefold(): urlsplit(url).hostname.lower().removeprefix('www.')
                            for name, url in zip(names, urls) if url}
        sources = unique_sources([s for name in names for s in search.search(
            render_query('identity', name=name, domain=supplied_domains.get(name.casefold(), ''), context=req['context'], geography=req['geography']),
            'discovery', domain=supplied_domains.get(name.casefold()))])
        if not sources:
            raise ResearchError('Discovery found no evidence. Add a product description or narrow the market.')
        result = analyst.ask(Discovery,
            load_prompt('identity.md'),
            {'request': req, 'sources': sources})
        competitors = Discovery.model_validate(result).model_dump()['competitors']
        by_name = {c['name'].strip().casefold(): c for c in competitors}
        if len(by_name) != 3 or set(by_name) != {name.casefold() for name in names}:
            raise ResearchError('Could not resolve the three supplied competitors. Refine their names or product context.')
        competitors = [dict(by_name[name.casefold()], name=name) for name in names]
        seen = set()
        ids = {s['id'] for s in sources}
        for c in competitors:
            domain = supplied_domains.get(c['name'].casefold(), c['domain'].lower().removeprefix('www.'))
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}', domain):
                raise ResearchError('Discovery returned an invalid official hostname; retry with more company context.')
            if domain in seen or c['name'].casefold().strip() == req['company'].casefold().strip():
                raise ResearchError('Discovery returned duplicate or self competitors. Refine the research scope.')
            c['source_ids'] = [sid for sid in c['source_ids'] if sid in ids]
            if not c['source_ids']:
                raise ResearchError('Discovery selected a competitor without evidence. Refine the research scope.')
            c['domain'] = domain
            seen.add(domain)
        return {'competitors': competitors, 'discovery_sources': sources,
                'events': ['Identity agent: resolved the three user-supplied competitors with supporting evidence.']}
