from __future__ import annotations
import os, io, time, tempfile
from pathlib import Path

BACKUP_DIR = Path("backups")

def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def _ensure_backup_dir() -> None:
    BACKUP_DIR.mkdir(exist_ok=True)

def _backup_file(p: Path) -> Path | None:
    try:
        if not p.exists():
            return None
        _ensure_backup_dir()
        bak = BACKUP_DIR / f"{p.name}.bak_{_timestamp()}"
        try:
            import shutil
            shutil.copy2(p, bak)
        except Exception:
            bak.write_bytes(p.read_bytes())
        return bak
    except Exception:
        return None

def _atomic_write_bytes(p: Path, data: bytes) -> None:
    _ensure_backup_dir()
    d = p.parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="._tmp_", dir=str(d))
    try:
        with io.FileIO(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def _atomic_write_text(p: Path, text: str, encoding="utf-8", errors=None) -> None:
    data = text.encode(encoding or "utf-8", errors or "strict")
    _atomic_write_bytes(p, data)

if not getattr(Path, "_vt_backup_wrapped", False):
    def _wrap_write_text(self: Path, data: str, encoding="utf-8", errors=None):
        _backup_file(self)
        _atomic_write_text(self, data, encoding=encoding, errors=errors)
        return len(data)

    def _wrap_write_bytes(self: Path, data: bytes):
        _backup_file(self)
        _atomic_write_bytes(self, data)
        return len(data)

    Path.write_text = _wrap_write_text
    Path.write_bytes = _wrap_write_bytes
    Path._vt_backup_wrapped = True
