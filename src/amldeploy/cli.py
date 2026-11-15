"""
Единая точка входа aml-deploy с подкомандами:
  build              собрать архив (env+jobs) из git         [dev/CI]
  list               показать распакованные сборки           [сервер]
  switch <name>      переключиться на сборку (+ Viya)         [сервер]
  release <archive>  распаковать, переключить, задеплоить     [сервер]
  deploy             только деплой job'ов/расписаний в Viya   [сервер]

Пути (aml-deploy.env, jobs/config.yaml, logs) выводятся из корня custom_config, который передаёт
лаунчер (--custom-config-root) или, по умолчанию, текущий каталог. Переменные окружения не нужны.
"""
import argparse
import os
import sys

from amldeploy import build as build_mod
from amldeploy import release as release_mod
from amldeploy.settings import resolve_settings


def _find_repo_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start or os.getcwd())
        d = parent


def _add_common(p):
    p.add_argument("--custom-config-root", default=None,
                   help="корень custom_config (обычно передаётся лаунчером); по умолчанию текущий каталог")
    p.add_argument("--env-file", default=None,
                   help="путь к env-файлу aml-deploy (по умолчанию <custom_config>/aml-deploy.env; для локальных API-тестов)")


def build_parser():
    p = argparse.ArgumentParser(prog="aml-deploy",
                                description="Единый инструмент сборки и разворачивания SAS AML")
    _add_common(p)
    sub = p.add_subparsers(dest="command", required=True)

    pb = sub.add_parser("build", help="собрать архив (env+jobs) из git")
    pb.add_argument("-n", "--name", default=None, help="имя сборки (по умолчанию — имя git-ветки)")
    pb.add_argument("-r", "--ref", default="HEAD", help="git-ref (по умолчанию HEAD)")
    pb.add_argument("-o", "--out", default=None, help="каталог для архива (по умолчанию deploy/dist)")

    sub.add_parser("list", help="показать распакованные сборки и активную")

    ps = sub.add_parser("switch", help="переключиться на распакованную сборку")
    ps.add_argument("name")
    ps.add_argument("--no-viya", action="store_true", help="не передеплоивать job'ы/расписания в Viya")

    pr = sub.add_parser("release", help="распаковать архив, переключить симлинки, задеплоить Viya")
    pr.add_argument("archive")
    pr.add_argument("--no-viya", action="store_true", help="не деплоить job'ы/расписания в Viya")
    pr.add_argument("--dry-run", action="store_true", help="Viya-шаг: показать, ничего не меняя")

    pd = sub.add_parser("deploy", help="только деплой job'ов/расписаний в Viya по текущему jobs/config.yaml")
    pd.add_argument("--dry-run", action="store_true")
    pd.add_argument("--allow-delete", action="store_true")
    pd.add_argument("--allow-delete-orphans", action="store_true")

    return p


def _run_viya(settings, dry_run=False, allow_delete=False, allow_delete_orphans=False):
    from amldeploy.viya import deploy as viya_deploy
    report = viya_deploy.run(
        settings, dry_run=dry_run, allow_delete=allow_delete, allow_delete_orphans=allow_delete_orphans
    )
    return 1 if report.summary["failed"] else 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = resolve_settings(args.custom_config_root, args.env_file)

    if args.command == "build":
        build_mod.run_build(_find_repo_root(), args.name, args.ref, args.out, settings=settings)
        return 0

    if args.command == "list":
        release_mod.list_builds(settings)
        return 0

    if args.command == "switch":
        release_mod.switch_to_build(settings, args.name)
        if args.no_viya:
            return 0
        return _run_viya(settings)

    if args.command == "release":
        release_mod.deploy_archive(settings, args.archive)
        if args.no_viya:
            return 0
        return _run_viya(settings, dry_run=args.dry_run)

    if args.command == "deploy":
        return _run_viya(
            settings, dry_run=args.dry_run,
            allow_delete=args.allow_delete, allow_delete_orphans=args.allow_delete_orphans,
        )

    return 2


if __name__ == "__main__":
    sys.exit(main())
