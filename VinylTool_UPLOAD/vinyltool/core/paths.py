from __future__ import annotations
from pathlib import Path
import json

# SOURCE_ROOT points to .../Vinyl_Listing_Tool/Source
SOURCE_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = SOURCE_ROOT / "profiles"
ACTIVE_FILE = PROFILES_DIR / "active_profile.json"

def get_active_profile() -> str:
    try:
        data = json.loads(ACTIVE_FILE.read_text())
        if isinstance(data, dict) and data.get("profile"):
            return str(data["profile"])
    except Exception:
        pass
    return "dev"

def profile_data_dir(profile: str | None = None) -> Path:
    p = profile or get_active_profile()
    return PROFILES_DIR / p / "data"

def path_config(profile: str | None = None) -> Path:
    return profile_data_dir(profile) / "config.json"

def path_db(profile: str | None = None) -> Path:
    return profile_data_dir(profile) / "inventory.db"

def path_geometry(profile: str | None = None) -> Path:
    return profile_data_dir(profile) / "geometry.conf"

def path_api_clients(profile: str | None = None) -> Path:
    return profile_data_dir(profile) / "api_clients.py"
