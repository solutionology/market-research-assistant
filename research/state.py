import operator
from typing import Annotated, TypedDict


class State(TypedDict, total=False):
    request: dict
    as_of: str
    competitors: list[dict]
    discovery_sources: list[dict]
    reports: Annotated[list[dict], operator.add]
    collated_reports: list[dict]
    events: Annotated[list[str], operator.add]
    synthesis: dict


class TeamState(TypedDict, total=False):
    request: dict
    as_of: str
    competitor: dict
    sources: list[dict]
    findings: dict
    attempt: int
    errors: list[str]
    events: list[str]
