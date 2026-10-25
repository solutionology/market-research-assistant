"""LangGraph coordination, bounded routing and final briefing synthesis."""
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from research.agents.identity import IdentityAgent
from research.agents.researcher import ResearchAgent
from research.agents.extractor import ExtractionAgent
from research.agents.reviewer import EvidenceReviewAgent
from research.state import State, TeamState
from research.evidence import unique_sources
from research.models import Synthesis
from research.quality import audit_synthesis
from research.prompts import load_prompt
from research.clients import ResearchError


class Orchestrator:
    def __init__(self, search, analyst):
        self.search = search
        self.analyst = analyst

    def synthesize(self, state):
        analyst = self.analyst
        reports = state['collated_reports']
        sources = unique_sources(state['discovery_sources'] + [s for r in reports for s in r['sources']])
        result = analyst.ask(Synthesis,
            load_prompt('orchestrator.md'),
            {'request': state['request'], 'reports': reports})
        return {'synthesis': audit_synthesis(result, sources, reports),
                'events': ['Orchestrator: compiled cross-competitor briefing and strategic implications.']}

    @staticmethod
    def collate(state):
        """Join all parallel teams before synthesis and restore the user's order."""
        reports = state['reports']
        by_domain = {report['competitor']['domain']: report for report in reports}
        expected = [competitor['domain'] for competitor in state['competitors']]
        if len(reports) != len(expected) or len(by_domain) != len(expected) or set(by_domain) != set(expected):
            raise ResearchError('Parallel research returned missing or duplicate competitor reports. Run the research again.')
        return {'collated_reports': [by_domain[domain] for domain in expected],
                'events': [f'Orchestrator: joined all {len(expected)} parallel competitor teams and collated their results.']}

    @staticmethod
    def route_review(state):
        findings = state['findings']
        missing = any(not findings[key] for key in ('features', 'positioning', 'news'))
        return 'gather' if state['attempt'] < 2 and missing else END

    @staticmethod
    def dispatch(state):
        return [Send('competitor_team', {'request': state['request'], 'as_of': state['as_of'],
                                        'competitor': competitor}) for competitor in state['competitors']]

    def build_graph(self, checkpointer=None):
        team = StateGraph(TeamState)
        team.add_node('gather', ResearchAgent(self.search))
        team.add_node('extract', ExtractionAgent(self.analyst))
        team.add_node('audit', EvidenceReviewAgent())
        team.add_edge(START, 'gather')
        team.add_edge('gather', 'extract')
        team.add_edge('extract', 'audit')
        team.add_conditional_edges('audit', self.route_review)
        compiled_team = team.compile()

        def competitor_team(state):
            result = compiled_team.invoke(state)
            return {'reports': [{'competitor': result['competitor'], 'findings': result['findings'],
                                 'sources': result['sources'], 'errors': result['errors']}],
                    'events': result['events']}

        graph = StateGraph(State)
        graph.add_node('discover', IdentityAgent(self.search, self.analyst))
        graph.add_node('competitor_team', competitor_team)
        graph.add_node('collate', self.collate)
        graph.add_node('synthesize', self.synthesize)
        graph.add_edge(START, 'discover')
        graph.add_conditional_edges('discover', self.dispatch, ['competitor_team'])
        # LangGraph joins this fan-out superstep before running collate once.
        graph.add_edge('competitor_team', 'collate')
        graph.add_edge('collate', 'synthesize')
        graph.add_edge('synthesize', END)
        return graph.compile(checkpointer=checkpointer)


def build_graph(search, analyst, checkpointer=None):
    return Orchestrator(search, analyst).build_graph(checkpointer)
