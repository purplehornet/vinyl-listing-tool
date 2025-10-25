from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from .paths import path_config

@dataclass
class Config:
    path: Path = field(default_factory=path_config)
    data: dict = field(default_factory=dict)

    def load(self) -> "Config":
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value


# --- Added shim: load_config() ---
def load_config():
    """Return the active config as a dict using paths.path_config()."""
    import json
    from .paths import path_config
    with open(path_config(), "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    """Persist config atomically to paths.path_config()."""
    import json, tempfile, os
    from .paths import path_config
    target = path_config()
    d = os.path.dirname(target)
    os.makedirs(d, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, prefix=".cfg_", suffix=".tmp", encoding="utf-8") as tmp:
        json.dump(cfg, tmp, ensure_ascii=False, indent=2)
        tmp.flush(); os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, target)
