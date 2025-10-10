from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from app.models import KnowledgeEntry, KnowledgeEntryPublic, TimelinePoint, TimelineResponse


class TimelineService:
    def build(self, entries: Iterable[KnowledgeEntry]) -> TimelineResponse:
        buckets: dict[datetime, list[KnowledgeEntryPublic]] = defaultdict(list)
        for entry in entries:
            bucket_start = entry.created_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if entry.created_at.tzinfo is None:
                bucket_start = bucket_start.replace(tzinfo=timezone.utc)
            buckets[bucket_start].append(KnowledgeEntryPublic.model_validate(entry))
        points: list[TimelinePoint] = []
        for start in sorted(buckets.keys()):
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
            points.append(TimelinePoint(period_start=start, period_end=end, entries=buckets[start]))
        return TimelineResponse(data=points)
