from research.formatting import claim_list_markdown, profile_markdown


def test_claims_render_as_separate_bullets_with_numbered_sources():
    sources = {'s1': {'url': 'https://example.com/features'}}
    claims = [dict(text='Supports approval workflows.', source_ids=['s1'], kind='fact', confidence='high'),
              dict(text='Evaluate workflow depth in a product trial.', source_ids=['s1'], kind='inference', confidence='medium')]
    text = claim_list_markdown(claims, sources)
    assert len([line for line in text.splitlines() if line.startswith('- ')]) == 2
    assert '[1](https://example.com/features)' in text
    assert '**Inference:**' in text
    assert claim_list_markdown([], sources).startswith('- No supported')


def test_briefing_does_not_repeat_profiles_or_other_briefing_sections():
    from research.formatting import briefing_synthesis, briefing_markdown
    feature = dict(text='Supports approval workflows.', source_ids=['s1'], kind='fact', confidence='high')
    implication = dict(text='Validate workflow depth through a buyer trial.', source_ids=['s1'], kind='inference', confidence='medium')
    report = dict(competitor=dict(name='Competitor A', rationale='Relevant workflow product'),
                  findings=dict(features=[feature], pricing=[feature], positioning=[], news=[], gaps=[]), errors=[])
    brief = dict(request=dict(company='Company', context='', geography='Global', news_days=30),
                 run_id='a' * 32, generated_at='2026-10-25', mode='live', competitors=[report],
                 synthesis=dict(executive_summary=[feature, implication], opportunities=[implication], watchlist=[]),
                 sources=[dict(id='s1', title='Product documentation', url='https://example.com/features',
                               retrieved_at='2026-10-25', published_at=None)], warnings=[])
    synthesis = briefing_synthesis(brief)
    assert synthesis['executive_summary'] == [implication]
    assert synthesis['opportunities'] == []
    text = briefing_markdown(brief)
    assert text.count('Supports approval workflows.') == 1
    assert '### Pricing' not in text
    assert '# Competitor profiles' in text
