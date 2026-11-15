"""
Оркестратор полного флоу деплоя job definitions + расписаний в SAS Viya. Порядок:
1) root_folder_path (создаётся, если нет — аддитивное действие, выполняется даже в dry-run).
2) по каждому модулю: папка модуля -> по каждому job'у: definition create/update/skip ->
   (если definition обновился — снять текущее расписание перед обновлением, пересоздать после) ->
   расписание reconcile (create/update/skip/remove) по текущему конфигу.
3) лишние файлы/пустые папки в managed-папках — report-only, либо удаление под allow_delete.
4) анализ jobRequest/scheduler по всему окружению: наши orphan, чужие на наших job'ах, битые ссылки.
5) отчёт (консоль + файл).

Клиент Viya создаётся здесь (ленивая инициализация): реквизиты читаются из settings.env_file_path (aml-deploy.env).
Возвращает Report; решение о коде возврата принимает вызывающий (cli).
"""
import requests

from amldeploy.env_file import load_env
from amldeploy.viya import cleanup, job_definitions, job_requests, orphans, scheduler
from amldeploy.viya.client import ViyaClient
from amldeploy.viya.config.loader import load_and_validate
from amldeploy.viya.folders import ensure_folder_path
from amldeploy.viya.reporting import Report


def _reconcile_schedule(client, folder_name, job, job_definition_uri, all_scheduler_jobs, dry_run, log):
    job_key = job_requests.build_job_key(folder_name, job["name"])
    name = job["name"]

    if "schedule" in job:
        req, _ = job_requests.ensure(client, name, job_definition_uri, job_key, dry_run=dry_run, log=log)
        if req is None:
            log(f"[schedule] '{name}': пропуск — jobRequest ещё не существует (dry-run для нового job'а)")
            return None
        return scheduler.ensure(client, name, req["id"], job["schedule"], all_scheduler_jobs, dry_run=dry_run, log=log)[1]

    existing_req = job_requests.find_managed_by_key(client, job_key)
    if existing_req is None:
        return None
    removed = scheduler.unschedule(client, existing_req["id"], all_scheduler_jobs, dry_run=dry_run, log=log)
    if dry_run:
        log(f"[dry-run] jobRequest '{name}': будет удалён (расписание в конфиге больше не задано)")
    else:
        job_requests.delete_request(client, existing_req["id"])
        log(f"[jobRequest] '{name}': удалён (расписание в конфиге больше не задано)")
    return "removed" if removed else None


def _teardown_before_update(client, folder_name, job, all_scheduler_jobs, dry_run, log):
    job_key = job_requests.build_job_key(folder_name, job["name"])
    existing_req = job_requests.find_managed_by_key(client, job_key)
    if existing_req is None:
        return
    scheduler.unschedule(client, existing_req["id"], all_scheduler_jobs, dry_run=dry_run, log=log)
    if dry_run:
        log(f"[dry-run] jobRequest '{job['name']}': будет пересоздан после обновления job definition")
    else:
        job_requests.delete_request(client, existing_req["id"])


def run(settings, dry_run=False, allow_delete=False, allow_delete_orphans=False,
        config_path=None, schema_path=None, report_prefix=None, verify=False, log=print):
    config_path = config_path or settings.jobs_config_path
    schema_path = schema_path or settings.jobs_schema_path
    report_prefix = report_prefix or settings.report_prefix

    config = load_and_validate(config_path, schema_path)
    log(f"[config] '{config_path}' загружен и провалидирован")

    env = load_env(settings.env_file_path)
    client = ViyaClient.from_env(env, verify=verify)
    log("[auth] токен получен")

    root_folder_path = config["root_folder_path"].rstrip("/")
    modules = config["modules"]
    report = Report()

    all_job_definition_uris = []
    expected_job_keys = set()

    for module in modules:
        folder_name = module["folder_name"]
        jobs = module["jobs"]
        log(f"\n--- Модуль '{folder_name}' ---")

        folder_uri = ensure_folder_path(client, f"{root_folder_path}/{folder_name}", log=log)
        all_scheduler_jobs = scheduler.find_all(client)

        for job in jobs:
            name = job["name"]
            try:
                result = job_definitions.deploy(client, folder_uri, job, dry_run=dry_run, log=log)
                all_job_definition_uris.append(result["job_definition_uri"])

                if result["action"] == "updated":
                    _teardown_before_update(client, folder_name, job, all_scheduler_jobs, dry_run, log)
                    all_scheduler_jobs = scheduler.find_all(client) if not dry_run else all_scheduler_jobs

                schedule_action = None
                if result["job_definition_uri"] is not None:
                    schedule_action = _reconcile_schedule(
                        client, folder_name, job, result["job_definition_uri"], all_scheduler_jobs, dry_run, log
                    )
                else:
                    log(f"[schedule] '{name}': пропуск — job definition будет создан только в реальном прогоне")

                if "schedule" in job:
                    expected_job_keys.add(job_requests.build_job_key(folder_name, name))

                report.add_job_result(folder_name, name, result["action"], schedule_action)
            except (requests.HTTPError, RuntimeError) as e:
                message = e.response.text if isinstance(e, requests.HTTPError) else str(e)
                log(f"[job] '{name}': ОШИБКА — {message}")
                report.add_job_result(folder_name, name, None, None, error=message)

        expected_names = [job["name"] for job in jobs]
        unexpected = cleanup.find_unexpected_members(client, folder_uri, expected_names, log=log)
        report.set_unexpected_members(folder_name, [cleanup.summarize_member(m) for m in unexpected])

        empty_folders = cleanup.find_empty_subfolders(client, unexpected) if unexpected else []
        report.set_empty_folders(folder_name, [cleanup.summarize_member(m) for m in empty_folders])

        if allow_delete and unexpected:
            for member in unexpected:
                if dry_run:
                    log(f"[dry-run] будет удалён лишний объект '{member['name']}'")
                else:
                    cleanup.delete_member(client, member)
                    report.add_deleted("member", member)
                    log(f"[cleanup] удалён лишний объект '{member['name']}'")

    log("\n--- Анализ jobRequest/scheduler по всему окружению ---")
    orphan_report = orphans.analyze(client, expected_job_keys, [u for u in all_job_definition_uris if u])
    report.set_orphans(orphan_report)

    if allow_delete_orphans and orphan_report["_raw_orphan_requests"]:
        all_sched = orphan_report["_all_scheduler_jobs"]
        for req in orphan_report["_raw_orphan_requests"]:
            if dry_run:
                log(f"[dry-run] orphan jobRequest '{req['name']}' будет удалён вместе с расписанием")
                continue
            scheduler.unschedule(client, req["id"], all_sched, dry_run=False, log=log)
            job_requests.delete_request(client, req["id"])
            report.add_deleted("jobRequest (orphan)", req)
            log(f"[cleanup] orphan jobRequest '{req['name']}' удалён вместе с расписанием")

    text_report = report.to_text()
    log(text_report)
    report.write(report_prefix)
    log(f"\n[report] сохранён в {report_prefix}.json / {report_prefix}.txt")

    return report
