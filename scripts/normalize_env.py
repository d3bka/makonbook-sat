#!/usr/bin/env python3
"""Normalize MakonBook .env without printing or changing secret values.

The current project historically accumulated repeated .env blocks. python-dotenv
uses the last assignment, so this script preserves that behavior while writing
one canonical copy based on .env.example. Unknown keys are kept at the end.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

OBSOLETE_KEYS = {
    "AI_GRADING_ENABLED",
    "AI_REPORT_ANALYSIS_ENABLED",
    "AI_REPORT_AUTO_APPLY_ENABLED",
    "AI_REPORT_AUTO_APPLY_MIN_CONFIDENCE",
}


def parse_assignments(path: Path) -> tuple[dict[str, str], list[str], int]:
    values: dict[str, str] = {}
    order: list[str] = []
    duplicates = 0
    if not path.exists():
        return values, order, duplicates
    for raw in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if key in values:
            duplicates += 1
        else:
            order.append(key)
        values[key] = value
    return values, order, duplicates


def normalize(env_path: Path, template_path: Path) -> tuple[str, int, int]:
    current, current_order, duplicates = parse_assignments(env_path)
    template_text = template_path.read_text(encoding="utf-8")
    template_keys: set[str] = set()
    output: list[str] = []

    for raw in template_text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in raw:
            key, default = raw.split("=", 1)
            key = key.strip()
            if key and key.replace("_", "").isalnum():
                template_keys.add(key)
                value = current.get(key, default)
                output.append(f"{key}={value}")
                continue
        output.append(raw)

    unknown = [key for key in current_order if key not in template_keys and key not in OBSOLETE_KEYS]
    obsolete = [key for key in current_order if key in OBSOLETE_KEYS]
    if unknown:
        output.extend([
            "",
            "# ----- Preserved custom/legacy variables -----",
            "# Review these manually; MakonBook may no longer read some of them.",
        ])
        for key in unknown:
            output.append(f"{key}={current[key]}")

    return "\n".join(output).rstrip() + "\n", duplicates, len(unknown), len(obsolete)


def atomic_write(path: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env", help="Environment file to normalize")
    parser.add_argument("--template", default=".env.example", help="Canonical template")
    parser.add_argument("--check", action="store_true", help="Report only; do not rewrite")
    args = parser.parse_args()

    env_path = Path(args.env)
    template_path = Path(args.template)
    if not env_path.exists():
        print(f"SKIP: {env_path} does not exist.")
        return 0
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    normalized, duplicates, unknown, obsolete = normalize(env_path, template_path)
    original = env_path.read_text(encoding="utf-8-sig")
    changed = original.replace("\r\n", "\n") != normalized
    print(f"{env_path}: duplicate assignments={duplicates}, preserved custom keys={unknown}, removed obsolete keys={obsolete}, needs_cleanup={changed}")
    if changed and not args.check:
        atomic_write(env_path, normalized)
        print(f"Normalized {env_path} atomically. Secret values were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
