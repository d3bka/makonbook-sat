#!/usr/bin/env python3
"""Safe MakonBook repository cleanup.

Removes generated/IDE/cache files, old unreferenced frontend leftovers, and
runtime credential exports without touching application data in PostgreSQL,
Cloudflare R2, the local .venv (unless explicitly requested), local media, or
local db.sqlite3.

It also removes historically tracked generated files from Git's index while
leaving local media/db files in place.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

GENERATED_DIRS = [
    ".idea",
    ".sixth",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "staticfiles",
]

LEGACY_STATIC_FILES = [
    "static/assets/css/makon-after-login-fix.css",
    "static/assets/css/makon-auth-show-balance-fix.css",
    "static/assets/css/makon-auth-show-desktop-fix.css",
    "static/assets/css/makon-auth-show-hard-fix.css",
    "static/assets/css/makon-faq-animation.css",
    "static/assets/css/makon-guest-review-v18.css",
    "static/assets/css/makon-math.css",
    "static/assets/css/sat-test-classic-v16.css",
    "static/assets/css/sat-test-flow-v14.css",
    "static/assets/css/support-booking-v29.css",
    "static/assets/js/bootstrap.min.js",
    "static/assets/js/jquery.min.js",
    "static/assets/js/support-booking-v29.js",
    "static/assets/js/test-import-progress.js",
]

# Generated Telegram exports can contain temporary plaintext credentials.
RUNTIME_CREDENTIAL_EXPORT_DIR = "apps/telegram_bot/requests"

GIT_UNTRACK_ONLY = [
    "db.sqlite3",
    "media",
]

GIT_UNTRACK_AND_REMOVE = [
    "staticfiles",
    ".idea",
    RUNTIME_CREDENTIAL_EXPORT_DIR,
]


def human_size(value: int) -> str:
    n = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            try:
                total += (Path(base) / name).stat().st_size
            except OSError:
                pass
    return total


def remove_path(path: Path, *, dry_run: bool) -> int:
    size = path_size(path)
    if not path.exists():
        return 0
    print(f"REMOVE  {path.relative_to(ROOT)} ({human_size(size)})")
    if dry_run:
        return size
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    return size


def remove_python_caches(*, dry_run: bool) -> tuple[int, int]:
    removed_files = 0
    removed_bytes = 0
    skip_roots = {".git", ".venv", "venv", "env", "ENV"}

    for base, dirs, files in os.walk(ROOT, topdown=True):
        base_path = Path(base)
        rel_parts = base_path.relative_to(ROOT).parts if base_path != ROOT else ()
        if rel_parts and rel_parts[0] in skip_roots:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_roots]

        if base_path.name == "__pycache__":
            size = path_size(base_path)
            print(f"REMOVE  {base_path.relative_to(ROOT)} ({human_size(size)})")
            removed_bytes += size
            if not dry_run:
                shutil.rmtree(base_path, ignore_errors=True)
            dirs[:] = []
            continue

        for name in files:
            if name.endswith((".pyc", ".pyo")):
                p = base_path / name
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                removed_files += 1
                removed_bytes += size
                if not dry_run:
                    p.unlink(missing_ok=True)

    if removed_files:
        print(f"REMOVE  {removed_files} loose .pyc/.pyo files ({human_size(removed_bytes)})")
    return removed_files, removed_bytes


def run_git(args: list[str], *, dry_run: bool) -> None:
    if not (ROOT / ".git").exists():
        return
    cmd = ["git", *args]
    print("GIT     " + " ".join(cmd))
    if dry_run:
        return
    subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def normalize_env(path_name: str, template_name: str, *, dry_run: bool) -> None:
    env_path = ROOT / path_name
    template = ROOT / template_name
    if not env_path.exists() or not template.exists():
        return
    cmd = [sys.executable, str(ROOT / "scripts" / "normalize_env.py"), "--env", str(env_path), "--template", str(template)]
    if dry_run:
        cmd.append("--check")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean generated MakonBook project clutter safely.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without deleting anything")
    parser.add_argument("--remove-venv", action="store_true", help="Also delete .venv (it can be recreated from requirements.txt)")
    parser.add_argument("--keep-staticfiles", action="store_true", help="Keep generated staticfiles locally (still untracked from Git)")
    parser.add_argument("--skip-env-normalize", action="store_true", help="Do not deduplicate/canonicalize local .env files")
    parser.add_argument("--skip-git-index", action="store_true", help="Do not clean historically tracked generated files from Git index")
    args = parser.parse_args()

    if not (ROOT / "manage.py").exists() or not (ROOT / "apps" / "sat").exists():
        raise SystemExit(f"Refusing to run outside MakonBook root: {ROOT}")

    print(f"MakonBook cleanup root: {ROOT}")
    print("Mode:", "DRY RUN" if args.dry_run else "APPLY")

    reclaimed = 0
    dirs = list(GENERATED_DIRS)
    if args.keep_staticfiles:
        dirs.remove("staticfiles")
    if args.remove_venv:
        dirs.append(".venv")

    for rel in dirs:
        reclaimed += remove_path(ROOT / rel, dry_run=args.dry_run)

    # Remove generated credential exports. The bot can regenerate a request file
    # from DB history if a manager requests a download later.
    reclaimed += remove_path(ROOT / RUNTIME_CREDENTIAL_EXPORT_DIR, dry_run=args.dry_run)

    _, cache_bytes = remove_python_caches(dry_run=args.dry_run)
    reclaimed += cache_bytes

    for rel in LEGACY_STATIC_FILES:
        reclaimed += remove_path(ROOT / rel, dry_run=args.dry_run)

    if not args.skip_env_normalize:
        normalize_env(".env", ".env.example", dry_run=args.dry_run)
        normalize_env(".env.production", ".env.production.example", dry_run=args.dry_run)

    if not args.skip_git_index and (ROOT / ".git").exists():
        for rel in GIT_UNTRACK_ONLY:
            run_git(["rm", "-r", "--cached", "--ignore-unmatch", rel], dry_run=args.dry_run)
        for rel in GIT_UNTRACK_AND_REMOVE:
            run_git(["rm", "-r", "--cached", "--ignore-unmatch", rel], dry_run=args.dry_run)

    print(f"Cleanup complete. Reclaimable/removed working-tree data: about {human_size(reclaimed)}")
    print("Preserved: .git, .venv (unless --remove-venv), local media, local db.sqlite3, migrations, source static assets, project docs.")
    if (ROOT / ".git").exists():
        print("Review with: git status --short")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
