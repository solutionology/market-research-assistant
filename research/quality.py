"""Deterministic evidence gates. Citation existence is not semantic fact checking."""
from datetime import datetime, timedelta
import re
from urllib.parse import urlsplit
from research.models import Findings, Synthesis


def host(domain):
    return urlsplit('https://' + domain).hostname or ''


def clean_claim(claim, allowed):
    ids = list(dict.fromkeys(s for s in claim['source_ids'] if s in allowed))
    if not ids:
        return None
    return {**claim, 'source_ids': ids}


def audit_findings(findings, sources, days, as_of):
    result = Findings.model_validate(findings).model_dump()
    allowed = {s['id'] for s in sources}
    gaps = list(result['gaps'])
    for section in ('features', 'positioning'):
        kept = []
        for claim in result[section]:
            checked = clean_claim(claim, allowed)
            if checked:
                kept.append(checked)
            else:
                gaps.append(f'Removed an unsupported {section} claim.')
        result[section] = kept
        if not kept:
            gaps.append(f'No supported {section} information found.')
    news = []
    end = datetime.fromisoformat(as_of).date()
    start = end - timedelta(days=days)
    for item in result['news']:
        checked = clean_claim(item['headline'], allowed)
        try:
            date = datetime.fromisoformat(item['published_on']).date()
            dated_support = any(s['id'] in item['headline']['source_ids'] and s.get('published_at')
                                and datetime.fromisoformat(s['published_at'].replace('Z', '+00:00')).date() == date
                                for s in sources)
        except (ValueError, TypeError):
            dated_support = False
            date = None
        if checked and dated_support and start <= date <= end:
            news.append({**item, 'headline': checked})
        else:
            gaps.append('Excluded news with missing, conflicting, future, or out-of-window publication dates.')
    result['news'] = news
    if not news:
        gaps.append(f'No date-verified news found in the last {days} days.')
    result['gaps'] = list(dict.fromkeys(gaps))
    return result


def audit_synthesis(synthesis, sources, reports=()):
    result = Synthesis.model_validate(synthesis).model_dump()
    allowed = {s['id'] for s in sources}
    normalize = lambda text: re.sub(r'\W+', ' ', text.casefold()).strip()
    seen = set()
    for report in reports:
        findings = report['findings']
        for section in ('features', 'positioning'):
            seen.update(normalize(claim['text']) for claim in findings.get(section, []))
        seen.update(normalize(item['headline']['text']) for item in findings.get('news', []))
    distinct = {}
    for key, claims in result.items():
        distinct[key] = []
        for claim in claims:
            checked = clean_claim(claim, allowed)
            text = normalize(claim['text'])
            if checked and text not in seen:
                distinct[key].append(checked)
                seen.add(text)
    return distinct
