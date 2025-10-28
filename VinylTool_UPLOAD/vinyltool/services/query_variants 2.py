# vinyltool/services/query_variants.py
import re
from typing import List

ALIASES = {
    "and": ["&"],
    "&": ["and"],
}

def strip_noise(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\(\)\[\]\{\}\.,:;!'\"]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def variants(artist: str, album: str) -> List[str]:
    base = strip_noise(f"{artist} {album}")
    out = {base}
    # swap and/&
    for a,b in [(" and ", " & "),(" & ", " and ")]:
        if a in base: out.add(base.replace(a,b))
    # remove stopwords common in listings
    out.add(re.sub(r"\b(limited edition|lp|vinyl|record|album|new|sealed)\b", "", base).strip())
    return [v for v in out if v]
