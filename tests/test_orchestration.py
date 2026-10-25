from threading import Barrier, Lock
import pytest
from research.clients import ResearchError
from research.models import Request, Findings, Synthesis
from research.orchestrator import Orchestrator, build_graph
from tests.fakes import FixtureSearch, FixtureAnalyst, SNAPSHOT


def test_teams_run_concurrently_and_collate_before_one_synthesis():
    # Each extraction must start before any can finish: a sequential graph times out.
    barrier = Barrier(3, timeout=10)
    lock = Lock()
    completed = []
    synthesis_calls = []
    class Analyst(FixtureAnalyst):
        def ask(self, schema, task, data):
            if schema is Findings:
                barrier.wait()
                result = super().ask(schema, task, data)
                with lock:
                    completed.append(data['competitor']['name'])
                return result
            if schema is Synthesis:
                assert set(completed) == {'Asana', 'monday.com', 'ClickUp'}
                synthesis_calls.append([report['competitor']['name'] for report in data['reports']])
            return super().ask(schema, task, data)
    request = Request(company='Notion', competitor_names=['ClickUp', 'Asana', 'monday.com'])
    state = build_graph(FixtureSearch(), Analyst()).invoke(
        dict(request=request.model_dump(), as_of=SNAPSHOT, reports=[], events=[]),
        {'max_concurrency': 3})
    assert synthesis_calls == [request.competitor_names]
    assert len(state['collated_reports']) == 3
    assert sum('joined all 3' in event for event in state['events']) == 1


def test_collation_rejects_missing_or_duplicate_results():
    state = {'competitors': [{'domain': 'one.com'}, {'domain': 'two.com'}],
             'reports': [{'competitor': {'domain': 'one.com'}}]}
    with pytest.raises(ResearchError, match='missing or duplicate'):
        Orchestrator.collate(state)
    state['reports'].append(state['reports'][0])
    with pytest.raises(ResearchError, match='missing or duplicate'):
        Orchestrator.collate(state)
