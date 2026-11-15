"""
CRUD scheduler job'ов. Scheduler НЕ поддерживает properties (проверено на сервере — значение всегда
возвращается null), поэтому "наш" scheduler job определяется косвенно: по ссылке request.uri на
"наш" (managedBy-помеченный) jobRequest.

Поддерживаются только minutely/hourly/daily (проверено на сервере) — monthly/weekly не нужны.

Важные находки с тестового прогона на сервере, зашитые в константы ниже:
- "hours" в триггере — это НЕ время старта, а список РАЗРЕШЁННЫХ часов через запятую
  (для minutely/hourly используем весь день "0,1,...,23", чтобы job работал непрерывно).
- "minutes" — минута срабатывания внутри разрешённого часа (для daily — минута самого запуска).
- "startDate" обязателен API, но не несёт для нас смысла — всегда подставляем сегодняшнюю дату и
  НЕ сравниваем её при определении "не изменилось ли расписание", иначе оно пересоздавалось бы каждый прогон.
"""
import datetime

SUPPORTED_SCHEDULE_TYPES = {"minutely", "hourly", "daily"}

DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_DURATION = 100
DEFAULT_RUN_AS = ""
DEFAULT_MAX_OCCURRENCE = -1
ALL_HOURS = ",".join(str(h) for h in range(24))
ANCHOR_MINUTE = "0"


def _today():
    return datetime.date.today().isoformat()


def build_trigger(schedule):
    sched_type = schedule["type"]
    if sched_type not in SUPPORTED_SCHEDULE_TYPES:
        raise ValueError(f"тип расписания '{sched_type}' не поддерживается (только: {SUPPORTED_SCHEDULE_TYPES})")

    if sched_type == "daily":
        hours, minutes = schedule["at"].split(":")
    else:
        hours, minutes = ALL_HOURS, ANCHOR_MINUTE

    return {
        "name": "schedule",
        "type": "timeevent",
        "runAs": DEFAULT_RUN_AS,
        "active": True,
        "recurrence": {
            "type": sched_type,
            "startDate": _today(),
            "skipCount": schedule.get("every", 1),
        },
        "hours": hours,
        "minutes": minutes,
        "duration": DEFAULT_DURATION,
        "timezone": schedule.get("timezone", DEFAULT_TIMEZONE),
        "maxOccurrence": DEFAULT_MAX_OCCURRENCE,
    }


def find_all(client):
    return client.get_all_items("/scheduler/jobs")


def find_for_job_request(client, job_request_id, all_scheduler_jobs=None):
    jobs = all_scheduler_jobs if all_scheduler_jobs is not None else find_all(client)
    needle = f"/jobExecution/jobRequests/{job_request_id}/"
    matches = [j for j in jobs if needle in (j.get("request") or {}).get("uri", "")]
    if len(matches) > 1:
        raise RuntimeError(f"Найдено более одного scheduler job для jobRequest {job_request_id}: {[m['id'] for m in matches]}")
    return matches[0] if matches else None


def create(client, name, job_request_id, schedule):
    payload = {
        "name": name,
        "request": {
            "uri": f"/jobExecution/jobRequests/{job_request_id}/jobs",
            "method": "POST",
            "headers": {"Accept": ["application/vnd.sas.job.execution.job+json"]},
        },
        "triggers": [build_trigger(schedule)],
    }
    return client.post_json("/scheduler/jobs", payload)


def delete_scheduler_job(client, scheduler_id):
    return client.delete(f"/scheduler/jobs/{scheduler_id}")


def schedule_matches(existing_scheduler_job, schedule):
    """startDate сознательно НЕ сравниваем — технически обязательное, но бессмысленное для нас поле;
    сравнение по нему приводило бы к пересозданию расписания при каждом запуске деплоя."""
    triggers = existing_scheduler_job.get("triggers") or []
    if len(triggers) != 1:
        return False
    trigger = triggers[0]
    rec = trigger.get("recurrence") or {}
    expected = build_trigger(schedule)
    expected_rec = expected["recurrence"]
    return (
        rec.get("type") == expected_rec["type"]
        and rec.get("skipCount") == expected_rec["skipCount"]
        and str(trigger.get("hours")) == str(expected["hours"])
        and str(trigger.get("minutes")) == str(expected["minutes"])
        and trigger.get("timezone") == expected["timezone"]
    )


def ensure(client, name, job_request_id, schedule, all_scheduler_jobs, dry_run=False, log=print):
    """Найти-или-создать расписание для jobRequest'а. Пересоздаёт при расхождении, не трогает при совпадении."""
    existing = find_for_job_request(client, job_request_id, all_scheduler_jobs)
    if existing is not None and schedule_matches(existing, schedule):
        log(f"[schedule] '{name}': расписание без изменений, пропуск")
        return existing, "skipped"

    if dry_run:
        verb = "будет пересоздано" if existing is not None else "будет создано"
        log(f"[dry-run] '{name}': расписание {verb}")
        return existing, ("would_update" if existing is not None else "would_create")

    if existing is not None:
        log(f"[schedule] '{name}': расписание отличается от конфига, пересоздаю")
        delete_scheduler_job(client, existing["id"])

    created = create(client, name, job_request_id, schedule)
    log(f"[schedule] '{name}': поставлен на расписание (id={created['id']})")
    return created, ("created" if existing is None else "updated")


def unschedule(client, job_request_id, all_scheduler_jobs, dry_run=False, log=print):
    """Снять с расписания, если jobRequest сейчас стоит в scheduler. True, если что-то удалили/было бы удалено."""
    existing = find_for_job_request(client, job_request_id, all_scheduler_jobs)
    if existing is None:
        return False
    if dry_run:
        log(f"[dry-run] расписание будет снято (scheduler id={existing['id']})")
        return True
    delete_scheduler_job(client, existing["id"])
    log(f"[schedule] снят с расписания (scheduler id={existing['id']})")
    return True
