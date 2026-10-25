from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from research.models import Source
from research.prompts import load_prompt


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def publication_date(value):
    """Normalize ISO and RFC 2822 dates returned by search providers."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        try:
            return parsedate_to_datetime(str(value)).date().isoformat()
        except (ValueError, TypeError, OverflowError):
            return None


def source_id(url: str) -> str:
    parts = urlsplit(url)
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))
    return 's-' + hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ResearchError(RuntimeError):
    """A user-safe provider failure; never contains keys or provider response bodies."""


class TemporarySearchError(Exception):
    pass


class TavilySearch:
    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
           retry=retry_if_exception_type((TemporarySearchError, httpx.TransportError)), reraise=True)
    def _post(self, payload):
        with httpx.Client(timeout=45) as client:
            response = client.post('https://api.tavily.com/search',
                                   headers={'Authorization': f'Bearer {self.api_key}'}, json=payload)
        if response.status_code == 429 or response.status_code >= 500:
            raise TemporarySearchError('Tavily temporarily unavailable or rate limited.')
        if response.status_code in (401, 403):
            raise ResearchError('Tavily rejected the API key. Check your credentials and account.')
        if response.is_error:
            raise ResearchError(f'Tavily search failed (HTTP {response.status_code}).')
        return response.json()

    def search(self, query, category, *, domain=None, days=30):
        payload = dict(query=query[:400], search_depth='advanced', max_results=5,
                       include_raw_content=False, include_answer=False,
                       topic='news' if category == 'news' else 'general')
        if domain:
            payload['include_domains'] = [domain]
        if category == 'news':
            payload['start_date'] = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
            payload['include_published_date'] = True
        try:
            data = self._post(payload)
        except (TemporarySearchError, httpx.TransportError) as exc:
            raise ResearchError('Tavily timed out or remained unavailable after three attempts.') from exc
        sources = []
        for row in data.get('results', []):
            url = row.get('url', '')
            if urlsplit(url).scheme not in ('http', 'https'):
                continue
            sources.append(Source(id=source_id(url), title=row.get('title', url), url=url,
                content=(row.get('content') or '')[:7000], category=category,
                published_at=publication_date(row.get('published_date')), retrieved_at=utcnow()).model_dump(mode='json'))
        return sources





class Analyst:
    def __init__(self, api_key, model):
        from langchain_openai import ChatOpenAI
        # OpenAI-compatible transport; all model requests go to OpenRouter.
        self.model = ChatOpenAI(api_key=api_key, model=model, temperature=0,
                               base_url='https://openrouter.ai/api/v1', use_responses_api=False,
                               extra_body={'provider': {'require_parameters': True}},
                               timeout=90, max_retries=2)

    def ask(self, schema, task, data):
        system_prompt = load_prompt('shared_system.md')
        try:
            return self.model.with_structured_output(schema, method='json_schema', strict=True).invoke([
                ('system', system_prompt + '\n' + task), ('human', json.dumps(data, ensure_ascii=False))
            ]).model_dump(mode='json')
        except Exception as exc:
            raise ResearchError('OpenRouter analysis failed. Check your OpenRouter API key, credits, model ID and structured-output support; run the research again to retry.') from exc
