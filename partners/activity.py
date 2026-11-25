from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import ListingClick


PILOT_TIME_ZONE = ZoneInfo("Europe/London")


def record_click(listing_id, action):
    day = timezone.localdate(timezone=PILOT_TIME_ZONE)
    row, _ = ListingClick.objects.get_or_create(listing_id=listing_id, day=day, action=action)
    ListingClick.objects.filter(pk=row.pk).update(count=F("count") + 1)


def with_recent_activity(queryset, relation="click_days"):
    today = timezone.localdate(timezone=PILOT_TIME_ZONE)
    window = Q(**{f"{relation}__day__range": (today - timedelta(days=29), today)})
    return queryset.annotate(**{
        f"{action}_clicks": Sum(
            f"{relation}__count", filter=window & Q(**{f"{relation}__action": action}), default=0,
        ) for action in ListingClick.Action.values
    })
