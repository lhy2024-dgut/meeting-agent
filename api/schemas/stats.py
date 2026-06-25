from pydantic import BaseModel


class DistributionItem(BaseModel):
    key: str
    label: str
    count: int


class TrendItem(BaseModel):
    month: str
    count: int


class StatsOverviewResponse(BaseModel):
    total_meetings: int
    short_meetings: int
    medium_meetings: int
    long_meetings: int
    multi_speaker_meetings: int
    duration_distribution: list[DistributionItem]
    environment_distribution: list[DistributionItem]
    monthly_trend: list[TrendItem]
