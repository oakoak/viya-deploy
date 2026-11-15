"""Сбор детального и сводного отчёта по деплою. Пишется и на консоль, и в файл (json + текст)."""
import json
import os


class Report:
    def __init__(self):
        self.modules = []  # [{folder_name, jobs: [...]}]
        self.summary = {
            "created": 0, "updated": 0, "skipped": 0, "failed": 0,
            "schedule_created": 0, "schedule_updated": 0, "schedule_skipped": 0, "schedule_removed": 0,
        }
        self.unexpected_members = {}   # folder_name -> [member summary]
        self.empty_folders = {}        # folder_name -> [member summary]
        self.orphans = None            # dict из orphans.analyze()
        self.deleted = []              # что реально удалили в этом прогоне (allow_delete)

    def _module(self, folder_name):
        for m in self.modules:
            if m["folder_name"] == folder_name:
                return m
        m = {"folder_name": folder_name, "jobs": []}
        self.modules.append(m)
        return m

    def add_job_result(self, folder_name, job_name, definition_action, schedule_action=None, error=None):
        entry = {"job_name": job_name, "definition_action": definition_action, "schedule_action": schedule_action, "error": error}
        self._module(folder_name)["jobs"].append(entry)
        if error:
            self.summary["failed"] += 1
            return
        if definition_action:
            self.summary[definition_action] += 1
        if schedule_action:
            self.summary[f"schedule_{schedule_action}"] += 1

    def set_unexpected_members(self, folder_name, members):
        if members:
            self.unexpected_members[folder_name] = members

    def set_empty_folders(self, folder_name, members):
        if members:
            self.empty_folders[folder_name] = members

    def set_orphans(self, orphans):
        self.orphans = {k: v for k, v in orphans.items() if not k.startswith("_")}

    def add_deleted(self, kind, item):
        self.deleted.append({"kind": kind, "id": item.get("id"), "name": item.get("name")})

    def to_dict(self):
        return {
            "summary": self.summary,
            "modules": self.modules,
            "unexpected_members": self.unexpected_members,
            "empty_folders": self.empty_folders,
            "orphans": self.orphans,
            "deleted": self.deleted,
        }

    def to_text(self):
        lines = []
        for module in self.modules:
            lines.append(f"\n--- Модуль '{module['folder_name']}' ---")
            for job in module["jobs"]:
                if job["error"]:
                    lines.append(f"  [{job['job_name']}] ОШИБКА: {job['error']}")
                else:
                    sched = f", schedule={job['schedule_action']}" if job["schedule_action"] else ""
                    lines.append(f"  [{job['job_name']}] definition={job['definition_action']}{sched}")

        if self.unexpected_members:
            lines.append("\n--- Лишние объекты в папках ---")
            for folder_name, members in self.unexpected_members.items():
                lines.append(f"  {folder_name}: {[m['name'] for m in members]}")

        if self.empty_folders:
            lines.append("\n--- Пустые папки ---")
            for folder_name, members in self.empty_folders.items():
                lines.append(f"  {folder_name}: {[m['name'] for m in members]}")

        if self.orphans:
            lines.append("\n--- Расписание: анализ jobRequest/scheduler ---")
            o = self.orphans
            if o.get("our_orphan_requests"):
                lines.append(f"  наши orphan jobRequest (кандидаты на удаление): {[r['name'] for r in o['our_orphan_requests']]}")
            if o.get("unmanaged_requests_on_our_definitions"):
                lines.append(f"  ВНИМАНИЕ, чужие jobRequest на наших job'ах: {[r['name'] for r in o['unmanaged_requests_on_our_definitions']]}")
            if o.get("broken_requests"):
                lines.append(f"  БИТЫЕ jobRequest (ссылка на удалённый jobDefinition): {[r['name'] for r in o['broken_requests']]}")
            if o.get("broken_schedulers"):
                lines.append(f"  БИТЫЕ scheduler job (ссылка на удалённый jobRequest): {[r['name'] for r in o['broken_schedulers']]}")
            if not any(o.get(k) for k in ["our_orphan_requests", "unmanaged_requests_on_our_definitions", "broken_requests", "broken_schedulers"]):
                lines.append("  аномалий не найдено")

        if self.deleted:
            lines.append("\n--- Удалено в этом прогоне ---")
            for d in self.deleted:
                lines.append(f"  {d['kind']}: {d['name']} (id={d['id']})")

        lines.append("\n=== Summary ===")
        for k, v in self.summary.items():
            lines.append(f"{k}: {v}")

        return "\n".join(lines)

    def write(self, path_prefix):
        os.makedirs(os.path.dirname(os.path.abspath(path_prefix)), exist_ok=True)
        with open(f"{path_prefix}.json", "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        with open(f"{path_prefix}.txt", "w", encoding="utf-8") as f:
            f.write(self.to_text())
