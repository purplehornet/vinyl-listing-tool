from pathlib import Path
import re

F = Path("discogs_auto_matcher.py")
s = F.read_text(encoding="utf-8")

sig = re.search(r"def\s+_try_exact_match\s*\(\s*self\s*,\s*identifiers\s*:\s*Dict\s*\)\s*->\s*Optional\[Tuple\[int,\s*Dict,\s*float\]\]\s*:\s*", s)
if not sig:
    raise SystemExit("Could not find _try_exact_match signature")

nxt = re.search(r"^\s*def\s+", s[sig.end():], re.MULTILINE)
if nxt:
    start, end = sig.start(), sig.end() + nxt.start()
    tail = s[end:]
else:
    start, end = sig.start(), len(s)
    tail = ""

new_func = '''
def _try_exact_match(self, identifiers: Dict) -> Optional[Tuple[int, Dict, float]]:
    """
    Safer 'exact match' path:
    - Only accept when normalised catno equality holds.
    - If eBay artist/album exist, also enforce both similarities >= 0.60.
    - Adds DEBUG lines under VINYL_DEBUG_MATCHER.
    """
    import os
    from difflib import SequenceMatcher

    def _norm(x: str) -> str:
        return (x or "").replace(" ", "").replace("-", "").strip().lower()

    e_artist = (identifiers.get("artist") or "").strip().lower()
    e_album  = (identifiers.get("album") or "").strip().lower()
    e_cat    = _norm(identifiers.get("catalog_number") or "")
    e_bar    = (identifiers.get("barcode") or "").strip()

    if e_cat:
        self._rate_limit()
        try:
            results = self.dc.search({"catno": identifiers["catalog_number"], "type": "release"})
            results = results if isinstance(results, list) else results.get("results", [])
        except Exception:
            results = []

        for res in results[:5]:
            d_cat = _norm(res.get("catno") or "")
            equal = (e_cat and d_cat and e_cat == d_cat)
            if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                print(f"DEBUG exact: catno e='{e_cat}' d='{d_cat}' equal={equal} id={res.get('id')} title='{(res.get('title') or '')[:80]}'")
            if not equal:
                continue

            d_title = (res.get("title") or "").strip().lower()
            d_artist, d_album = "", ""
            if " - " in d_title:
                d_artist, d_album = [p.strip() for p in d_title.split(" - ", 1)]
            else:
                d_artist = (res.get("artist") or "").strip().lower()
                d_album  = d_title

            if e_artist and d_artist:
                a_sim = SequenceMatcher(None, e_artist, d_artist).ratio()
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print(f"DEBUG exact: a_sim={a_sim:.2f} e='{e_artist}' d='{d_artist}'")
                if a_sim < 0.60:
                    continue
            if e_album and d_album:
                t_sim = SequenceMatcher(None, e_album, d_album).ratio()
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print(f"DEBUG exact: t_sim={t_sim:.2f} e='{e_album}' d='{d_album}'")
                if t_sim < 0.60:
                    continue

            release_id = res.get("id")
            if release_id:
                try:
                    release_data = self.dc.get_release(release_id)
                except Exception:
                    release_data = None
                return (release_id, release_data, 0.95)

    if e_bar:
        self._rate_limit()
        try:
            results = self.dc.search({"barcode": e_bar, "type": "release"})
            results = results if isinstance(results, list) else results.get("results", [])
        except Exception:
            results = []

        for res in results[:3]:
            d_title = (res.get("title") or "").strip().lower()
            d_artist, d_album = "", ""
            if " - " in d_title:
                d_artist, d_album = [p.strip() for p in d_title.split(" - ", 1)]
            else:
                d_artist = (res.get("artist") or "").strip().lower()
                d_album  = d_title

            ok = True
            if e_artist and d_artist:
                a_sim = SequenceMatcher(None, e_artist, d_artist).ratio()
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print(f"DEBUG exact(barcode): a_sim={a_sim:.2f} e='{e_artist}' d='{d_artist}'")
                if a_sim < 0.60:
                    ok = False
            if e_album and d_album:
                t_sim = SequenceMatcher(None, e_album, d_album).ratio()
                if os.getenv("VINYL_DEBUG_MATCHER") == "1":
                    print(f"DEBUG exact(barcode): t_sim={t_sim:.2f} e='{e_album}' d='{d_album}'")
                if t_sim < 0.60:
                    ok = False

            if not ok:
                continue

            release_id = res.get("id")
            if release_id:
                try:
                    release_data = self.dc.get_release(release_id)
                except Exception:
                    release_data = None
                return (release_id, release_data, 0.98)

    return None
'''.lstrip("\n")

new_src = s[:sig.start()] + new_func + s[end:]
F.write_text(new_src, encoding="utf-8")
print("✅ _try_exact_match patched.")
