import json
import os
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError
from research.clients import ResearchError
from research.formatting import briefing_markdown, briefing_synthesis, claim_list_markdown, profile_markdown, safe_text
from research.models import Request
from research.storage import list_saved_searches, load_saved_search, load_review, save_review
from research.runner import ROOT, run_research

load_dotenv(ROOT / '.env')
st.set_page_config(page_title='Market research assistant', page_icon=':material/travel_explore:', layout='wide')
st.session_state.setdefault('briefing', None)
if st.session_state.briefing and st.session_state.briefing.get('mode') != 'live':
    st.session_state.briefing = None
st.session_state.pop('pending_run', None)


def credential(name):
    try:
        return st.secrets.get(name, '') or os.getenv(name, '')
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(name, '')


def reset_new_research():
    if st.session_state.view == 'New research':
        st.session_state.briefing = None
        fields = ['company', 'geography', 'context', 'feature_focus', 'news_days']
        fields += [f'competitor_{i}' for i in range(1, 4)]
        fields += [f'competitor_url_{i}' for i in range(1, 4)]
        for field in fields:
            st.session_state.pop(field, None)


with st.sidebar:
    st.subheader('Research workspace')
    view = st.selectbox('View', ['New research', 'Saved searches'], key='view', on_change=reset_new_research)
    st.caption('Only completed live research is saved. Credentials are loaded from local configuration.')

st.caption('COMPETITIVE INTELLIGENCE / RESEARCH WORKSPACE')
st.title('Know the competitive landscape')
st.markdown('Choose three competitors and turn a research question into an evidence-backed briefing.')

if view == 'Saved searches':
    st.subheader('Saved searches')
    st.button('Refresh history', icon=':material/refresh:')
    history = list_saved_searches()
    query = st.text_input('Filter saved searches', placeholder='Company or competitor name').strip().casefold()
    history = [row for row in history if query in ' '.join([row['company'], *row['competitors']]).casefold()]
    if not history:
        st.info('No completed live searches found. Run research to create your first saved briefing.')
        st.session_state.briefing = None
    else:
        by_id = {row['run_id']: row for row in history}
        selected = st.selectbox('Saved briefing', list(by_id), key='saved_search',
            format_func=lambda sid: f"{by_id[sid]['company']} · {by_id[sid]['generated_at'][:19]} · {', '.join(by_id[sid]['competitors'])} · {sid[:8]}")
        try:
            st.session_state.briefing = load_saved_search(selected)
        except (OSError, ValueError):
            st.error('This saved briefing could not be loaded. Refresh the history and try again.')
            st.session_state.briefing = None
else:
    with st.form('research_request'):
        a, b = st.columns([2, 1])
        company = a.text_input('Company', placeholder='Enter your company', max_chars=120, key='company')
        geography = b.text_input('Target market', placeholder='For example: Global or United Kingdom', max_chars=100, key='geography')
        competitor_names, competitor_urls = [], []
        for i, col in enumerate(st.columns(3)):
            competitor_names.append(col.text_input(f'Competitor {i + 1}', placeholder='Enter competitor name',
                                    max_chars=120, key=f'competitor_{i + 1}'))
            competitor_urls.append(col.text_input(f'Competitor {i + 1} website (optional)',
                                   placeholder='https://www.example.com', max_chars=2048,
                                   key=f'competitor_url_{i + 1}',
                                   help='Enter the official website including https://. Leave blank to resolve it automatically.'))
        context = st.text_area('Product and buyer context', placeholder='Describe the product, buyers and research question',
                              max_chars=1200, height=80, key='context')
        feature_focus = st.text_input('Core features to research', placeholder='For example: case management, rule configuration, integrations', max_chars=1200, key='feature_focus')
        news_days = st.slider('News lookback (days)', 1, 365, 30, key='news_days')
        submitted = st.form_submit_button('Run live research', type='primary', icon=':material/travel_explore:')
    st.caption('Resolve your competitors → 3 parallel competitor teams → collect all reports → executive briefing')
    st.caption('9 initial Tavily searches, up to 6 follow-ups. API charges apply.')
    if submitted and (not company.strip() or not geography.strip()):
        st.error('Enter a company and target market to start research.')
        submitted = False
    if submitted:
        try:
            request = Request(company=company.strip(), competitor_names=competitor_names, competitor_urls=competitor_urls,
                              geography=geography.strip(), context=context, feature_focus=feature_focus, news_days=news_days)
        except ValidationError as exc:
            st.error(' '.join(error['msg'].removeprefix('Value error, ') for error in exc.errors()))
            submitted = False
    if submitted:
        with st.status('Research agents working', expanded=True) as status:
            try:
                output = run_research(request, tavily_key=credential('TAVILY_API_KEY'),
                    openrouter_key=credential('OPENROUTER_API_KEY'),
                    model=credential('OPENROUTER_MODEL') or 'openai/gpt-4.1-mini', on_event=st.write)
                st.session_state.briefing = output
                status.update(label='Live briefing complete and saved', state='complete', expanded=False)
            except ResearchError as exc:
                status.update(label='Research did not complete', state='error')
                st.error(str(exc))
                st.caption('This attempt was not saved. Previous completed searches remain available in Saved searches.')
            except Exception:
                status.update(label='Research did not complete', state='error')
                st.error('The pipeline was interrupted. This attempt was not saved. Please try again.')

brief = st.session_state.briefing
if brief:
    sources = {s['id']: s for s in brief['sources']}
    st.header(f"Competitive briefing · {safe_text(brief['request']['company'])}")
    st.caption(f"As of {brief['generated_at'][:10]} · {brief['request']['geography']} · {brief['request']['news_days']}-day news window")
    a, b, c = st.columns(3)
    a.metric('Competitors', len(brief['competitors']))
    b.metric('Unique sources', len(sources))
    c.metric('Dated news signals', sum(len(r['findings']['news']) for r in brief['competitors']))
    overview, profiles, evidence, activity = st.tabs(['Briefing', 'Competitor profiles', 'Evidence library', 'Agent activity'])
    with overview:
        st.caption('Cross-competitor implications and recommended decisions. Detailed capabilities and news are in Competitor profiles.')
        synthesis = briefing_synthesis(brief)
        for key, heading in [('executive_summary', 'Executive readout'), ('opportunities', 'Strategic opportunities'), ('watchlist', 'What to watch')]:
            st.subheader(heading)
            st.markdown(claim_list_markdown(synthesis[key], sources))
    with profiles:
        st.caption('Evidence-backed detail for each competitor: core features, positioning, recent news and gaps.')
        for report in brief['competitors']:
            with st.container(border=True):
                st.subheader(report['competitor']['name'])
                st.markdown(profile_markdown(report, sources))
    with evidence:
        for index, source in enumerate(brief['sources'], 1):
            with st.expander(f"{index}. {source['title']}"):
                st.link_button('Open source', source['url'])
                st.caption(f"Published: {source['published_at'] or 'Unknown'} · Retrieved: {source['retrieved_at']}")
                st.text(source['content'])
        for warning in brief['warnings']:
            st.caption(warning)
    with activity:
        st.caption('Operational activity log, showing research steps and outcomes.')
        for event in brief['events']:
            st.markdown('- ' + safe_text(event))
        st.caption(f"Run ID: {brief['run_id']}")
    a, b = st.columns(2)
    a.download_button('Download briefing', briefing_markdown(brief), file_name='competitor-briefing.md',
                      mime='text/markdown', icon=':material/download:')
    b.download_button('Download structured data', json.dumps(brief, indent=2, ensure_ascii=False),
                      file_name='competitor-briefing.json', mime='application/json', icon=':material/data_object:')

    with st.expander('Review this briefing'):
        st.caption('Check the cited sources, requested feature coverage and strategic implications before using this briefing in a product decision.')
        if brief.get('duration_seconds') is not None:
            st.caption(f"Automated research time: {brief['duration_seconds']:.0f} seconds. This excludes your input and review time.")
        try:
            review = load_review(brief['run_id'])
        except (OSError, ValueError):
            review = None
        with st.form(f"review_{brief['run_id']}"):
            usable = st.checkbox('This briefing is usable for my research question', value=bool(review and review['usable']))
            minutes = st.number_input('Total task time in minutes', min_value=0.1, max_value=1440.0,
                                      value=review['total_task_minutes'] if review else None, step=0.5,
                                      help='Time from starting the research form through reviewing the final briefing. Record your measured time.')
            notes = st.text_area('Review notes', value=review['notes'] if review else '', max_chars=2000)
            save = st.form_submit_button('Save review')
        if save:
            if minutes is None:
                st.error('Enter your measured total task time before saving the review.')
            else:
                try:
                    review = save_review(brief['run_id'], dict(usable=usable, total_task_minutes=minutes, notes=notes))
                    st.success('Review saved. This does not approve or change a product roadmap.')
                except (OSError, ValueError):
                    st.error('The review could not be saved. Please try again.')
        if review:
            target_met = review['usable'] and review['total_task_minutes'] < 10
            st.caption(f"Review recorded · {'Meets' if target_met else 'Does not meet'} the proposed usable-briefing-in-under-10-minutes target.")
