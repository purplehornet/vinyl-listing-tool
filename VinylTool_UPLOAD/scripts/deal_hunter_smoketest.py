#!/usr/bin/env python3
from __future__ import annotations
import sys, yaml, tkinter as tk
from pathlib import Path
sys.path.insert(0, ".")
from vinyltool.core.config import load_config
from vinyltool.services.ebay import EbayAPI
from vinyltool.services.ebay_search import EbaySearch
from vinyltool.services.discogs import DiscogsAPI
from vinyltool.services.smart_matcher import SmartMatcher

def load_searches(path="searches/searches.yaml"):
    y = yaml.safe_load(Path(path).read_text("utf-8"))
    return y.get("defaults", {}), y.get("searches", [])

def build_query(s, defaults):
    mode = s.get("mode","catno")
    if mode == "catno":
        q = s["catno"]
        if s.get("label"): q = f'{q} "{s["label"]}"'
        return q
    if mode == "artist_title":
        inc = " ".join(f'"{t}"' for t in s.get("include_terms",[]))
        exc = " ".join(f'-{t}' for t in s.get("exclude_terms", defaults.get("exclude_terms", [])))
        return f'"{s["artist"]}" "{s["title"]}" {inc} {exc}'.strip()
    return s.get("query","")

def fnum(v):
    try: return float(v)
    except: return 0.0

def detect_format(title: str, defaults: dict, fallback_formats: list[str]) -> str:
    t = title.lower()
    vs = defaults.get("format_terms",{}).get("vinyl_include", [])
    cs = defaults.get("format_terms",{}).get("cassette_include", [])
    if any(x in t for x in cs): return "cassette"
    if any(x in t for x in vs): return "vinyl"
    return (fallback_formats or ["vinyl"])[0]

def net_discogs(price, defaults, fmt: str):
    fees = defaults.get("price_model",{}).get("fees",{})
    d_pct = fees.get("discogs_pct", 0.09)
    d_pay = fees.get("discogs_payment_pct", 0.029)
    d_fix = fees.get("discogs_fixed", 0.30)
    pf = defaults.get("price_model",{}).get(fmt, {})
    outbound = pf.get("outbound_postage_gbp", 4.50)
    mailer = pf.get("mailer_cost_gbp", 0.50)
    return price * (1 - d_pct - d_pay) - d_fix - outbound - mailer

def fmt_thresholds(defaults, fmt: str):
    pf = defaults.get("price_model",{}).get(fmt, {})
    return pf.get("min_profit_gbp", 10.0), pf.get("min_margin_pct", 20.0)


    matcher = SmartMatcher(verbose=False)
def main():
    # Initialize smart matcher
    matcher = SmartMatcher(verbose=False)

    defaults, searches = load_searches()
    cfg = load_config()
    dc = DiscogsAPI(cfg)
    root = tk.Tk(); root.withdraw()
    try:
        eb = EbayAPI(cfg, root)
    except TypeError:
        eb = EbayAPI(cfg)
    es = EbaySearch(ebay_api=eb, site="EBAY_GB")

    print("\n=== Deal Hunter — Profit View ===\n")
    any_shown = False

    for s in searches:
        search_name = s.get("name", "")
        q = build_query(s, defaults)
        listing_types = s.get("listing_types", defaults.get("listing_types", ["BIN","AUCTION_BIN"]))
        max_price = s.get("max_price", defaults.get("max_price", 9999))
        excl = [t.lower() for t in s.get("exclude_terms", defaults.get("exclude_terms", []))]
        formats = s.get("formats", ["vinyl"])
        categories = []
        if "cassette" in [f.lower() for f in formats]:
            categories.append("Cassettes")
        if "vinyl" in [f.lower() for f in formats]:
            categories.append("Records")
        try:
            items = es.search_active_listings(
                query=q, limit=40, listing_types=listing_types, sort="newlyListed",
                price_cap=max_price, country="GB", categories=categories or None
            )
        except Exception as e:
            print(f"[{s['name']}] search error: {e}")
            continue

        rid = s.get("discogs_release_id")
        basis = 0.0
        if rid:
            ps = dc.get_price_suggestions(int(rid)) or {}
            vg = fnum((ps.get("Very Good Plus (VG+)",{}) or {}).get("value"))
            nm = fnum((ps.get("Near Mint (NM or M-)",{}) or {}).get("value"))
            basis = nm or vg or 0.0

        ranked = []
        for it in items:
            title = it["title"].strip()
            tl = title.lower()
            if any(b in tl for b in excl):
                continue
            fmt = detect_format(title, defaults, formats)
            buy = it["total"]
            if buy <= 0 or buy > max_price:
                continue
            if rid and basis > 0:
                target_net = net_discogs(basis, defaults, fmt)
                proj = target_net - buy
                margin = (proj / buy * 100.0) if buy > 0 else 0.0
                min_profit, min_margin = fmt_thresholds(defaults, fmt)
                seller_ok = (it.get("seller_fb_pct") or 100.0) >= defaults.get("seller_min_feedback_pct", 98)
                bad_cass = False
                if fmt == "cassette":
                    bad_terms = [t.lower() for t in defaults.get("cassette_bad_terms", [])]
                    if any(bt in tl for bt in bad_terms):
                        bad_cass = True
                # Smart match validation
                is_valid, match_confidence, match_reasons = matcher.match(
                    {'title': title, 'price': buy},
                    {'format': 'Cassette' if fmt == 'cassette' else 'Vinyl', 'median_price': basis},
                    search_name  # Use search name as proxy for Discogs title
                )
                
                if not is_valid:
                    # Rejected by smart matcher - skip silently
                    # Uncomment to see rejections:
                    # print(f"  ❌ REJECTED: {title[:60]}")
                    # for reason in match_reasons:
                    #     print(f"     {reason}")
                    continue
                
                
                if seller_ok and not bad_cass and proj >= min_profit and margin >= min_margin:
                    ranked.append((proj, margin, buy, fmt, it))
            else:
                ranked.append((0.0, 0.0, buy, fmt, it))


        ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
        positive = [r for r in ranked if r[0] > 0]
        shown = positive[:5] if positive else ranked[:3]

        if shown and positive:
            any_shown = True
            print(f"[{s['name']}] best candidates (Discogs basis {'£'+str(round(basis,2)) if basis else 'n/a'})")
            for proj, margin, buy, fmt, it in shown:
                head = f"£{proj:>6.2f} ({margin:>5.1f}%) on £{buy:>6.2f}"
                print(f"  {head} [{fmt}] | {it['title']}\n    {it['url']}")
            print()
        else:
            # Show near-misses if nothing cleared thresholds
            near = []
            for proj, margin, buy, fmt, it in ranked:
                # only consider items with a computed projection
                if proj == 0.0 and margin == 0.0:
                    continue
                min_profit, min_margin = fmt_thresholds(defaults, fmt)
                if (proj >= (min_profit - 5.0)) or (margin >= (min_margin - 5.0)):
                    near.append((proj, margin, buy, fmt, it))
            near.sort(key=lambda x: (x[0], x[1]), reverse=True)
            near = near[:3]
            if near:
                any_shown = True
                print(f"[{s['name']}] near misses (within £5 or 5% of threshold; Discogs basis {'£'+str(round(basis,2)) if basis else 'n/a'})")
                for proj, margin, buy, fmt, it in near:
                    head = f"£{proj:>6.2f} ({margin:>5.1f}%) on £{buy:>6.2f}"
                    print(f"  {head} [{fmt}] | {it['title']}\n    {it['url']}")
                print()
    if not any_shown:
        print("No profit-positive candidates yet. Try raising max_price or adding discogs_release_id to a search.")

if __name__ == "__main__":
    main()
