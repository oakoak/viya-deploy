import pytest

from amldeploy.viya import scheduler


def test_build_trigger_daily_uses_at_time():
    t = scheduler.build_trigger({"type": "daily", "every": 2, "at": "03:15"})
    assert t["hours"] == "03"
    assert t["minutes"] == "15"
    assert t["recurrence"]["type"] == "daily"
    assert t["recurrence"]["skipCount"] == 2
    assert t["timezone"] == scheduler.DEFAULT_TIMEZONE


def test_build_trigger_hourly_runs_all_day():
    t = scheduler.build_trigger({"type": "hourly", "every": 5})
    assert t["hours"] == scheduler.ALL_HOURS
    assert t["minutes"] == scheduler.ANCHOR_MINUTE
    assert t["recurrence"]["skipCount"] == 5


def test_build_trigger_minutely_custom_tz():
    t = scheduler.build_trigger({"type": "minutely", "every": 10, "timezone": "Europe/Kyiv"})
    assert t["hours"] == scheduler.ALL_HOURS
    assert t["timezone"] == "Europe/Kyiv"


def test_build_trigger_rejects_unsupported():
    with pytest.raises(ValueError):
        scheduler.build_trigger({"type": "weekly", "every": 1})


def test_schedule_matches_ignores_startdate():
    sched = {"type": "daily", "every": 1, "at": "03:00"}
    existing = {"triggers": [scheduler.build_trigger(sched)]}
    # startDate внутри триггера сегодняшняя, но matches его не сравнивает
    assert scheduler.schedule_matches(existing, sched)


def test_schedule_matches_false_on_time_change():
    existing = {"triggers": [scheduler.build_trigger({"type": "daily", "every": 1, "at": "03:00"})]}
    assert not scheduler.schedule_matches(existing, {"type": "daily", "every": 1, "at": "04:00"})


def test_schedule_matches_false_on_multiple_triggers():
    assert not scheduler.schedule_matches({"triggers": [{}, {}]}, {"type": "daily", "every": 1, "at": "03:00"})
