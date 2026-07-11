import config
from fastapi import APIRouter, Depends

from api.deps import get_current_user, get_meeting_repository
from api.schemas.stats import DistributionItem, StatsOverviewResponse, TrendItem
from db.repository import MeetingRepository

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=StatsOverviewResponse)
def get_stats_overview(
    repo: MeetingRepository = Depends(get_meeting_repository),
    current_user=Depends(get_current_user),
) -> StatsOverviewResponse:
    stats = repo.get_stats_overview_data(user_id=current_user.id)

    duration_distribution = [
        DistributionItem(
            key=key,
            label=config.DURATION_LABELS.get(key, key),
            count=stats["duration_distribution"].get(key, 0),
        )
        for key in ("short", "medium", "long")
    ]
    environment_distribution = [
        DistributionItem(
            key=key,
            label=config.ENV_LABELS.get(key, key),
            count=stats["environment_distribution"].get(key, 0),
        )
        for key in ("quiet", "noisy", "multi_speaker")
    ]
    monthly_trend = [
        TrendItem(month=item["month"], count=item["count"])
        for item in stats["monthly_trend"]
    ]

    return StatsOverviewResponse(
        total_meetings=stats["total_meetings"],
        short_meetings=stats["short_meetings"],
        medium_meetings=stats["medium_meetings"],
        long_meetings=stats["long_meetings"],
        multi_speaker_meetings=stats["multi_speaker_meetings"],
        duration_distribution=duration_distribution,
        environment_distribution=environment_distribution,
        monthly_trend=monthly_trend,
    )
