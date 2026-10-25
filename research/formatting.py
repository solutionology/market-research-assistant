from urllib.parse import urlsplit
from research.quality import audit_synthesis


def briefing_synthesis(brief):
    """Keep copied profile bullets out of the briefing, including older saved runs."""
    return audit_synthesis(brief['synthesis'], brief['sources'], brief['competitors'])


def safe_text(text):
    """Keep external text out of Markdown/HTML link syntax."""
    return str(text).replace('<', '&lt;').replace('>', '&gt;').replace('[', '\\[').replace(']', '\\]').replace('`', "'")


def claim_markdown(claim, sources):
    refs = []
    numbers = {sid: index for index, sid in enumerate(sources, 1)}
    for sid in claim['source_ids']:
        if sid in sources:
            url = str(sources[sid]['url'])
            if urlsplit(url).scheme in ('https', 'http'):
                url = url.replace('(', '%28').replace(')', '%29')
                refs.append(f'[{numbers[sid]}]({url})')
    label = '**Inference:** ' if claim['kind'] == 'inference' else ''
    text = safe_text(' '.join(claim['text'].split()))
    return f"{label}{text} _({claim['confidence']} confidence)_ " + ' '.join(refs)


def claim_list_markdown(claims, sources):
    return '\n'.join('- ' + claim_markdown(claim, sources) for claim in claims) or '- No supported information found.'


def profile_markdown(report, sources):
    competitor, findings = report['competitor'], report['findings']
    lines = [f"- **Scope relevance:** {safe_text(competitor['rationale'])}"]
    for key, title in [('features', 'Core features'), ('positioning', 'Market positioning')]:
        lines.extend([f'\n### {title}\n', claim_list_markdown(findings[key], sources)])
    lines.append('\n### Recent news\n')
    lines.extend(f"- **{item['published_on']}:** {claim_markdown(item['headline'], sources)}" for item in findings['news'])
    if not findings['news']:
        lines.append('- No date-verified news found in the selected window.')
    lines.append('\n### Gaps and limitations\n')
    gaps = findings['gaps'] + report['errors']
    lines.extend('- ' + safe_text(gap) for gap in gaps)
    if not gaps:
        lines.append('- No additional gaps reported.')
    return '\n'.join(lines)


def briefing_markdown(brief):
    if hasattr(brief, 'model_dump'):
        brief = brief.model_dump(mode='json')
    sources = {source['id']: source for source in brief['sources']}
    synthesis = briefing_synthesis(brief)
    lines = [f"# Competitor briefing: {safe_text(brief['request']['company'])}\n",
             f"- **Generated:** {brief['generated_at']}",
             f"- **Scope:** {safe_text(brief['request']['context']) or 'Not specified'}",
             f"- **Feature focus:** {safe_text(brief['request'].get('feature_focus', '')) or 'Core product capabilities'}",
             f"- **Market:** {safe_text(brief['request']['geography'])}",
             f"- **News lookback:** {brief['request']['news_days']} days",
             f"- **Search ID:** {brief['run_id']}"]
    for key, title in [('executive_summary', 'Executive summary'), ('opportunities', 'Strategic opportunities'), ('watchlist', 'Watchlist')]:
        lines.extend([f'\n## {title}\n', claim_list_markdown(synthesis[key], sources)])
    lines.append('\n# Competitor profiles\n')
    for report in brief['competitors']:
        lines.extend([f"\n## {safe_text(report['competitor']['name'])}\n", profile_markdown(report, sources)])
    lines.append('\n## Research limitations\n')
    lines.extend('- ' + safe_text(warning) for warning in brief['warnings'])
    lines.append('\n## Sources\n')
    for index, source in enumerate(brief['sources'], 1):
        lines.append(f"- **{index}.** [{safe_text(source['title'])}]({source['url']}) — published {source['published_at'] or 'unknown'}; retrieved {source['retrieved_at']}")
    return '\n'.join(lines) + '\n'
