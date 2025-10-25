#!/usr/bin/env python3
# Idempotent patcher for Deals Monitor integration.
# - Creates timestamped backups for *every* file it touches.
# - Safe to run multiple times; only inserts missing blocks.
#
# Usage:
#   /usr/bin/python3 tools/apply_patches.py --dry-run
#   /usr/bin/python3 tools/apply_patches.py

import re, sys, json, shutil, datetime
from pathlib import Path

DRY = "--dry-run" in sys.argv

# --- Repo-aware paths (adjust if your layout differs) ---
REPO_ROOT = Path(".").resolve()
CORE_MATCHER = REPO_ROOT / "vinyltool/core/discogs_auto_matcher.py"
SERV_MATCHER = REPO_ROOT / "vinyltool/services/discogs_auto_matcher.py"
SERV_DIR     = REPO_ROOT / "vinyltool/services"
UI_DIR       = REPO_ROOT / "vinyltool/ui"
SCRIPTS_DIR  = REPO_ROOT / "scripts"
PROFILE_DATA = REPO_ROOT / "profiles/dev/data"
CONF_EXAMPLE = PROFILE_DATA / "deals_config.json.example"
PHRASES_YML  = PROFILE_DATA / "condition_phrases.yml"

NEW_FILES = {
    SERV_DIR / "deal_ranker.py": "vinyltool/services/deal_ranker.py",
    SERV_DIR / "query_variants.py": "vinyltool/services/query_variants.py",
    SERV_DIR / "rate_limiter.py": "vinyltool/services/rate_limiter.py",
    UI_DIR / "deals_tab.py": "vinyltool/ui/deals_tab.py",
}

BANNER = """
# === Deals Monitor Integration ===
# This file was introduced by tools/apply_patches.py
# All changes are backed up timestamped as .bak_YYYYmmdd_HHMMSS
"""

def ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def backup(p: Path):
    if not p.exists():
        return None
    bak = p.with_name(p.name + f".bak_{ts()}")
    if not DRY:
        shutil.copy2(p, bak)
    print(f"  ↳ backup: {p} -> {bak}")
    return bak

def ensure_parent(p: Path):
    if not DRY:
        p.parent.mkdir(parents=True, exist_ok=True)

def write_if_missing(path: Path, content: str):
    ensure_parent(path)
    if path.exists():
        # do not overwrite if already present
        print(f"  = exists, skip: {path}")
        return
    print(f"  + create: {path}")
    if not DRY:
        path.write_text(content, encoding="utf-8")

def insert_once(path: Path, pattern: str, block: str):
    if not path.exists():
        print(f"  ! missing: {path} (skipped)")
        return
    s = path.read_text(encoding="utf-8")
    if re.search(pattern, s, re.DOTALL|re.MULTILINE):
        print(f"  = already present in: {path}")
        return
    print(f"  * patching: {path}")
    backup(path)
    if not DRY:
        s2 = s.rstrip() + "\n\n" + block + "\n"
        path.write_text(s2, encoding="utf-8")

def main():
    print("== Deals Monitor: apply patches ==")
    # 1) Drop in new modules if missing
    for dst, label in NEW_FILES.items():
        write_if_missing(dst, f"""{BANNER}

# {label}
# Minimal stub; Agent Mode will flesh this out.
if __name__ == "__main__":
    print("{label} stub OK")
""")
    # 2) Ensure config/example files
    ensure_parent(CONF_EXAMPLE)
    if not CONF_EXAMPLE.exists():
        print(f"  + create: {CONF_EXAMPLE}")
        cfg = {
            "modes": ["ending_soon","newly_listed","best_match"],
            "cadence_minutes": {"ending_soon":5,"newly_listed":10,"best_match":30},
            "price": {"max_total": 35.0, "min_profit": 8.0, "min_margin_pct": 35},
            "discogs": {"anchor":"p25","min_confidence":"high","unknown_price":"ignore"},
            "condition_markdowns": {"NM":0.0,"VG+":-0.10,"VG":-0.25,"G":-0.60},
            "seller": {"min_feedback_pct": 98.0, "min_count": 50},
            "geo": {"allow":["GB"], "max_shipping": 7.50},
            "keywords": {"positive":[],"negative":["warped","stock photo"]},
            "ranking": {"preset":"Balanced"}
        }
        if not DRY:
            CONF_EXAMPLE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    else:
        print(f"  = exists, skip: {CONF_EXAMPLE}")

    ensure_parent(PHRASES_YML)
    if not PHRASES_YML.exists():
        print(f"  + create: {PHRASES_YML}")
        yml = """# Condition and risk phrases (weights)
good:
  - { phrase: "nm", weight: 6 }
  - { phrase: "near mint", weight: 6 }
  - { phrase: "sealed", weight: 8 }
  - { phrase: "first press", weight: 5 }
  - { phrase: "a1/b1", weight: 4 }
  - { phrase: "porky", weight: 3 }
bad:
  - { phrase: "warped", weight: -8 }
  - { phrase: "split seam", weight: -5 }
  - { phrase: "water damage", weight: -6 }
  - { phrase: "stock photo", weight: -3 }
  - { phrase: "no cover", weight: -4 }
"""
        if not DRY:
            PHRASES_YML.write_text(yml, encoding="utf-8")
    else:
        print(f"  = exists, skip: {PHRASES_YML}")

    # 3) Advertise Deals tab entry point in UI
    deals_tab_stub = f"""{BANNER}

def register_deals_tab(app):
    """Register a 'Deals Monitor' tab. Wire this into your UI bootstrap."""
    # TODO: hook into your framework's tab system
    print("Deals Monitor tab registered (stub).")
"""
    insert_once(UI_DIR / "deals_tab.py", r"register_deals_tab\(", deals_tab_stub)

    print("== Done ==")

if __name__ == "__main__":
    main()
