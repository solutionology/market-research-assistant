from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, TypeAdapter, field_validator, model_validator


class Request(BaseModel):
    company: str = Field(min_length=1, max_length=120)
    competitor_names: list[str] = Field(min_length=3, max_length=3)
    competitor_urls: list[str | None] = Field(default_factory=lambda: [None, None, None], min_length=3, max_length=3)
    context: str = Field(default="", max_length=1200)
    feature_focus: str = Field(default="", max_length=1200)
    geography: str = Field(default="Global", min_length=1, max_length=100)
    news_days: int = Field(default=30, ge=1, le=365)

    @field_validator('competitor_urls')
    @classmethod
    def validate_urls(cls, urls):
        normalized = []
        for value in urls:
            if not value or not value.strip():
                normalized.append(None)
                continue
            url = TypeAdapter(HttpUrl).validate_python(value.strip())
            if url.username or url.password:
                raise ValueError('Website URLs must not contain login credentials.')
            normalized.append(str(url))
        return normalized

    @field_validator('competitor_names')
    @classmethod
    def validate_competitors(cls, names):
        names = [name.strip() for name in names]
        if any(not name or len(name) > 120 for name in names):
            raise ValueError('Enter three competitor names, each between 1 and 120 characters.')
        if len({name.casefold() for name in names}) != 3:
            raise ValueError('Enter three distinct competitor names.')
        return names

    @model_validator(mode='after')
    def exclude_focal_company(self):
        if self.company.strip().casefold() in {name.casefold() for name in self.competitor_names}:
            raise ValueError('Competitor names must differ from the focal company.')
        return self


class Source(BaseModel):
    id: str
    title: str
    url: HttpUrl
    content: str
    category: Literal["discovery", "pricing", "product", "news"]  # pricing is retained only for older saved sources
    retrieved_at: str
    published_at: str | None = None


class Competitor(BaseModel):
    name: str
    domain: str = Field(description="Official website hostname only, e.g. asana.com")
    rationale: str = Field(description="Product relevance of this user-supplied competitor to the research scope")
    source_ids: list[str]


class Discovery(BaseModel):
    competitors: list[Competitor] = Field(min_length=3, max_length=3)


class Claim(BaseModel):
    text: str
    source_ids: list[str] = Field(description="IDs from provided evidence supporting this claim")
    kind: Literal["fact", "inference"]
    confidence: Literal["high", "medium", "low"]


class NewsItem(BaseModel):
    headline: Claim
    published_on: str = Field(description="Publication date YYYY-MM-DD, never retrieval date")


class Findings(BaseModel):
    features: list[Claim]
    positioning: list[Claim]
    news: list[NewsItem]
    gaps: list[str] = Field(description="Missing information, conflicts, and limitations")


class Synthesis(BaseModel):
    executive_summary: list[Claim] = Field(description="Cross-competitor patterns, tradeoffs and implications; do not repeat profile details")
    opportunities: list[Claim] = Field(description="Product hypotheses and concrete validation steps grounded in feature evidence")
    watchlist: list[Claim] = Field(description="Forward-looking signals and questions to monitor, rather than repeated news headlines")


class Briefing(BaseModel):
    run_id: str
    generated_at: str
    duration_seconds: float | None = Field(default=None, ge=0)
    mode: Literal["live"]
    request: Request
    competitors: list[dict]
    synthesis: Synthesis
    sources: list[Source]
    warnings: list[str]
    events: list[str]


class HumanReview(BaseModel):
    usable: bool
    total_task_minutes: float = Field(gt=0, le=1440, description='PM-measured time from entering the request through reviewing the briefing')
    notes: str = Field(default='', max_length=2000)
    reviewed_at: str
