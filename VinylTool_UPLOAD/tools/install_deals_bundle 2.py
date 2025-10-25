#!/usr/bin/env python3
import argparse, shutil, sys, time
from pathlib import Path

ALLOWED_TOPS = {"vinyltool", "profiles", "scripts", "tools", "ui"}
TS = time.strftime("%Y%m%d_%H%M%S")

def iter_bundle_files(bundle_root: Path):
    # Copy anything under allowed top-level dirs
    for top in ALLOWED_TOPS:
        base = bundle_root / top
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file():
                    yield p

def main():
    ap = argparse.ArgumentParser(description="Install DealsMonitor bundle with backups.")
    ap.add_argument("--bundle", required=True, help="Path to DealsMonitor_Agent_Bundle")
    ap.add_argument("--dry-run", action="store_true", help="Preview only")
    args = ap.parse_args()

    repo_root = Path.cwd()
    bundle_root = (repo_root / args.bundle).resolve()
    if not bundle_root.exists():
        print(f"❌ Bundle path not found: {bundle_root}", file=sys.stderr)
        sys.exit(2)

    to_copy = list(iter_bundle_files(bundle_root))
    if not to_copy:
        print("ℹ️ No allowed top-levels found in bundle (vinyltool/profiles/scripts/tools/ui).")
        sys.exit(0)

    print(f"== Installing from: {bundle_root}")
    print(f"== Repo root      : {repo_root}")
    print(f"== Files detected : {len(to_copy)}")
    print()

    changed = 0
    for src in to_copy:
        rel = src.relative_to(bundle_root)
        dst = repo_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        # backup if exists
        if dst.exists():
            bak = dst.with_suffix(dst.suffix + f".bak_{TS}")
            print(f"[backup] {dst} -> {bak}")
            if not args.dry_run:
                shutil.copy2(dst, bak)
        # copy
        print(f"[write ] {dst}")
        if not args.dry_run:
            shutil.copy2(src, dst)
        changed += 1

    print()
    print(f"== Done. {changed} file(s) {'would be ' if args.dry_run else ''}installed.")
    if args.dry_run:
        print("   (Run again without --dry-run to apply.)")

if __name__ == "__main__":
    main()
