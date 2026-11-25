from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .schemas import ScheduledItem

ZONE = ZoneInfo("America/New_York")


def local_time(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=ZONE)


def city_days(request):
    return [
        request.cities[min(day * len(request.cities) // request.days, len(request.cities) - 1)]
        for day in range(request.days)
    ]


def schedule_violations(request, items):
    violations = []
    ordered = sorted(items, key=lambda x: x.start)
    previous = None
    daily_walk = {}
    for item in ordered:
        if item.start.tzinfo is None or item.end.tzinfo is None or item.end <= item.start:
            violations.append({"code": "INVALID_INTERVAL", "item": item.id})
            continue
        if item.start < item.opening_start or item.end > item.opening_end:
            violations.append({"code": "OUTSIDE_OPERATING_WINDOW", "item": item.id})
        if previous and previous.day == item.day:
            earliest = previous.end + timedelta(minutes=item.transfer_minutes + item.buffer_minutes)
            if item.start < earliest:
                violations.append(
                    {
                        "code": "TRANSFER_CONFLICT",
                        "item": item.id,
                        "shortfall_minutes": int((earliest - item.start).total_seconds() / 60),
                    }
                )
        if item.day == 0 and item.start < local_time(request.start_date, request.gateway_start_hour):
            violations.append({"code": "GATEWAY_START_CONFLICT", "item": item.id})
        if item.day == request.days - 1 and item.end > local_time(
            request.start_date + timedelta(days=item.day), request.gateway_end_hour
        ):
            violations.append({"code": "GATEWAY_END_CONFLICT", "item": item.id})
        daily_walk[item.day] = daily_walk.get(item.day, 0) + item.walk_meters
        previous = item
    for traveler in request.travelers:
        for day, meters in daily_walk.items():
            # Includes a fixed 500m/day station/lodging assumption in addition to activity walking.
            if meters + 500 > traveler.maximum_walk_meters:
                violations.append(
                    {
                        "code": "WALK_LIMIT",
                        "traveler": traveler.id,
                        "day": day,
                        "actual_meters": meters + 500,
                        "cap_meters": traveler.maximum_walk_meters,
                    }
                )
    return violations


def scheduled_activity(option, day_index, day_date, start):
    return ScheduledItem(
        id=f"activity-{day_index}-{option['id']}",
        activity_id=option["id"],
        day=day_index,
        city=option["city"],
        start=start,
        end=start + timedelta(minutes=option["duration_minutes"]),
        opening_start=local_time(day_date, option["open_hour"]),
        opening_end=local_time(day_date, option["close_hour"]),
        transfer_minutes=30,
        buffer_minutes=15,
        walk_meters=option["walk_meters"],
        evidence_state=option["schedule_state"],
    )
