#!/usr/bin/env python3
from __future__ import annotations
import sys, yaml, time, json
from pathlib import Path
from datetime import datetime, timezone

SOURCE_ROOT = Path("/Users/phil/Desktop/Vinyl_Listing_Tool/Source")
sys.path.insert(0, str(SOURCE_ROOT))

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_pass(msg): print(f"{Colors.GREEN}✅ PASS{Colors.END} - {msg}")
def print_fail(msg): print(f"{Colors.RED}❌ FAIL{Colors.END} - {msg}")
def print_warn(msg): print(f"{Colors.YELLOW}⚠️  WARN{Colors.END} - {msg}")
def print_info(msg): print(f"{Colors.BLUE}ℹ️  INFO{Colors.END} - {msg}")
def print_header(msg): print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}\n{msg}\n{'='*60}{Colors.END}")

class ValidationReport:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.warnings = 0
    
    def record_pass(self):
        self.tests_run += 1
        self.tests_passed += 1
    
    def record_fail(self):
        self.tests_run += 1
        self.tests_failed += 1
    
    def record_warn(self):
        self.warnings += 1
    
    def print_summary(self):
        print_header("VALIDATION SUMMARY")
        print(f"Total Tests: {self.tests_run}")
        print(f"{Colors.GREEN}Passed: {self.tests_passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.tests_failed}{Colors.END}")
        print(f"{Colors.YELLOW}Warnings: {self.warnings}{Colors.END}")
        score = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\n{Colors.BOLD}Score: {score:.1f}%{Colors.END}")
        if score >= 90:
            print(f"{Colors.GREEN}🎉 Ready for GUI integration!{Colors.END}")
        elif score >= 70:
            print(f"{Colors.YELLOW}⚠️  Some issues to fix before GUI work{Colors.END}")
        else:
            print(f"{Colors.RED}❌ Critical issues - fix before proceeding{Colors.END}")

report = ValidationReport()

def test_file_structure():
    print_header("TEST 1: File Structure & Dependencies")
    required_files = [
        "scripts/deal_hunter_smoketest.py",
        "scripts/deal_hunter_watch.py",
        "searches/searches.yaml",
        "searches/discovery.yaml",
        "vinyltool/core/config.py",
        "vinyltool/core/paths.py",
        "vinyltool/services/ebay_search.py",
        "vinyltool/services/discogs.py",
        "profiles/dev/data/config.json",
    ]
    for fpath in required_files:
        full_path = SOURCE_ROOT / fpath
        if full_path.exists():
            print_pass(f"Found: {fpath}")
            report.record_pass()
        else:
            print_fail(f"Missing: {fpath}")
            report.record_fail()
    for dpath in ["logs", "profiles/dev/data"]:
        full_path = SOURCE_ROOT / dpath
        full_path.mkdir(parents=True, exist_ok=True)
        print_info(f"Ensured directory exists: {dpath}")

def test_config():
    print_header("TEST 2: Config & API Tokens")
    try:
        from vinyltool.core.config import load_config
        cfg = load_config()
        print_pass("Config loaded successfully")
        report.record_pass()
        required_keys = {
            "discogs_token": "Discogs Personal Token",
            "ebay_app_id": "eBay App ID",
            "ebay_cert_id": "eBay Cert ID",
            "ebay_user_token": "eBay User Token",
        }
        for key, label in required_keys.items():
            val = cfg.get(key)
            if val:
                val_str = str(val)
                masked = val_str[:8] + "..." + val_str[-8:] if len(val_str) > 16 else "***"
                print_pass(f"{label} present: {masked}")
                report.record_pass()
            else:
                print_fail(f"{label} missing in config")
                report.record_fail()
        return cfg
    except Exception as e:
        print_fail(f"Config loading failed: {e}")
        report.record_fail()
        return None

def test_yaml_parsing():
    print_header("TEST 3: YAML File Parsing")
    searches_path = SOURCE_ROOT / "searches/searches.yaml"
    try:
        with open(searches_path, "r") as f:
            searches_data = yaml.safe_load(f)
        defaults = searches_data.get("defaults", {})
        searches = searches_data.get("searches", [])
        print_pass(f"searches.yaml loaded: {len(searches)} searches defined")
        report.record_pass()
        if "price_model" in defaults:
            print_pass("price_model found in defaults")
            report.record_pass()
        else:
            print_fail("price_model missing from defaults")
            report.record_fail()
        valid_count = 0
        zero_count = 0
        for s in searches:
            rid = s.get("discogs_release_id")
            if rid and rid > 0:
                valid_count += 1
            elif rid == 0:
                zero_count += 1
        print_info(f"  Valid release IDs: {valid_count}")
        print_info(f"  Zero release IDs: {zero_count}")
        if valid_count > 0:
            print_pass(f"At least {valid_count} searches have valid release_ids")
            report.record_pass()
        else:
            print_warn("No searches have valid release_ids")
            report.record_warn()
    except Exception as e:
        print_fail(f"searches.yaml parsing failed: {e}")
        report.record_fail()
    discovery_path = SOURCE_ROOT / "searches/discovery.yaml"
    try:
        with open(discovery_path, "r") as f:
            discovery_data = yaml.safe_load(f)
        disc_searches = discovery_data.get("searches", [])
        print_pass(f"discovery.yaml loaded: {len(disc_searches)} discovery patterns")
        report.record_pass()
    except Exception as e:
        print_fail(f"discovery.yaml parsing failed: {e}")
        report.record_fail()

def test_discogs_api(cfg):
    print_header("TEST 4: Discogs API Connection")
    if not cfg:
        print_fail("Skipping - no config available")
        report.record_fail()
        return None
    try:
        from vinyltool.services.discogs import DiscogsAPI
        dc = DiscogsAPI(cfg)
        if dc.is_connected():
            print_pass(f"Connected as: {dc.connected_username}")
            report.record_pass()
        else:
            print_fail("Discogs client not connected")
            report.record_fail()
            return None
        test_release_id = 249504
        print_info(f"Testing price fetch for release {test_release_id}...")
        time.sleep(1.2)
        prices = dc.get_price_suggestions(test_release_id)
        if prices:
            print_pass(f"Price suggestions fetched: {len(prices)} conditions")
            report.record_pass()
            for condition, data in list(prices.items())[:2]:
                value = data.get("value") if isinstance(data, dict) else data
                if value:
                    print_info(f"  {condition}: £{value:.2f}")
        else:
            print_warn("Price fetch returned empty (may be rate-limited)")
            report.record_warn()
        return dc
    except Exception as e:
        print_fail(f"Discogs API test failed: {e}")
        report.record_fail()
        return None

def test_ebay_api(cfg):
    print_header("TEST 5: eBay API Connection")
    if not cfg:
        print_fail("Skipping - no config available")
        report.record_fail()
        return None
    try:
        import tkinter as tk
        from vinyltool.services.ebay import EbayAPI
        from vinyltool.services.ebay_search import EbaySearch
        root = tk.Tk()
        root.withdraw()
        try:
            eb = EbayAPI(cfg, root)
        except TypeError:
            eb = EbayAPI(cfg)
        print_pass("eBay API client initialized")
        report.record_pass()
        es = EbaySearch(ebay_api=eb, site="EBAY_GB")
        print_info("Testing eBay search for 'Oasis vinyl'...")
        time.sleep(2.0)
        items = es.search_active_listings(query="Oasis vinyl", limit=5, listing_types=["BIN"], country="GB")
        if items:
            print_pass(f"eBay search returned {len(items)} items")
            report.record_pass()
            if len(items) > 0:
                item = items[0]
                print_info(f"  Sample: {item['title'][:60]}...")
                print_info(f"  Price: £{item['price']:.2f} + £{item['shipping']:.2f} shipping")
        else:
            print_warn("eBay search returned no results")
            report.record_warn()
        return es
    except Exception as e:
        print_fail(f"eBay API test failed: {e}")
        report.record_fail()
        return None

def test_profit_calculation():
    print_header("TEST 6: Profit Calculation Logic")
    searches_path = SOURCE_ROOT / "searches/searches.yaml"
    try:
        with open(searches_path, "r") as f:
            data = yaml.safe_load(f)
        defaults = data.get("defaults", {})
        print_info("Testing vinyl profit calculation...")
        discogs_price = 50.0
        ebay_cost = 20.0
        fees = defaults.get("price_model", {}).get("fees", {})
        vinyl_model = defaults.get("price_model", {}).get("vinyl", {})
        d_pct = fees.get("discogs_pct", 0.09)
        d_pay = fees.get("discogs_payment_pct", 0.029)
        d_fix = fees.get("discogs_fixed", 0.30)
        outbound = vinyl_model.get("outbound_postage_gbp", 4.50)
        mailer = vinyl_model.get("mailer_cost_gbp", 0.50)
        net_discogs = discogs_price * (1 - d_pct - d_pay) - d_fix - outbound - mailer
        profit = net_discogs - ebay_cost
        margin = (profit / ebay_cost * 100) if ebay_cost > 0 else 0
        print_info(f"  Discogs price: £{discogs_price:.2f}")
        print_info(f"  eBay cost: £{ebay_cost:.2f}")
        print_info(f"  Net after fees: £{net_discogs:.2f}")
        print_info(f"  Profit: £{profit:.2f} ({margin:.1f}%)")
        if abs(net_discogs - 40.63) < 0.5:
            print_pass("Vinyl profit calculation correct")
            report.record_pass()
        else:
            print_warn(f"Vinyl calculation may be off (expected ~£40.63)")
            report.record_warn()
        print_info("\nTesting cassette profit calculation...")
        cass_model = defaults.get("price_model", {}).get("cassette", {})
        cass_outbound = cass_model.get("outbound_postage_gbp", 2.50)
        cass_mailer = cass_model.get("mailer_cost_gbp", 0.35)
        cass_net = discogs_price * (1 - d_pct - d_pay) - d_fix - cass_outbound - cass_mailer
        print_info(f"  Cassette net: £{cass_net:.2f}")
        if cass_net > net_discogs:
            print_pass("Cassette has lower costs (correct)")
            report.record_pass()
        else:
            print_fail("Cassette calculation error")
            report.record_fail()
    except Exception as e:
        print_fail(f"Profit calculation test failed: {e}")
        report.record_fail()

def test_format_detection():
    print_header("TEST 7: Format Detection Logic")
    searches_path = SOURCE_ROOT / "searches/searches.yaml"
    try:
        with open(searches_path, "r") as f:
            data = yaml.safe_load(f)
        defaults = data.get("defaults", {})
        vinyl_terms = [t.lower() for t in defaults.get("format_terms", {}).get("vinyl_include", [])]
        cassette_terms = [t.lower() for t in defaults.get("format_terms", {}).get("cassette_include", [])]
        test_cases = [
            ("Oasis LP Vinyl", "vinyl"),
            ("The Cure Cassette", "cassette"),
            ("Depeche Mode 12\"", "vinyl"),
            ("Ministry Tape", "cassette"),
        ]
        for title, expected in test_cases:
            tl = title.lower()
            detected = "cassette" if any(t in tl for t in cassette_terms) else "vinyl"
            if detected == expected:
                print_pass(f"'{title}' → {detected}")
                report.record_pass()
            else:
                print_fail(f"'{title}' → {detected} (expected {expected})")
                report.record_fail()
    except Exception as e:
        print_fail(f"Format detection test failed: {e}")
        report.record_fail()

def test_exclude_filtering():
    print_header("TEST 8: Exclude Terms Filtering")
    searches_path = SOURCE_ROOT / "searches/searches.yaml"
    try:
        with open(searches_path, "r") as f:
            data = yaml.safe_load(f)
        defaults = data.get("defaults", {})
        exclude_terms = [t.lower() for t in defaults.get("exclude_terms", [])]
        test_cases = [
            ("Oasis Original Press", False),
            ("Depeche Mode 180g Reissue", True),
            ("The Cure Bootleg", True),
            ("New Order Vinyl", False),
        ]
        for title, should_exclude in test_cases:
            tl = title.lower()
            excluded = any(term in tl for term in exclude_terms)
            if excluded == should_exclude:
                action = "excluded" if excluded else "included"
                print_pass(f"'{title}' correctly {action}")
                report.record_pass()
            else:
                print_fail(f"'{title}' filtering incorrect")
                report.record_fail()
    except Exception as e:
        print_fail(f"Exclude filtering test failed: {e}")
        report.record_fail()

def test_state_persistence():
    print_header("TEST 9: State Persistence")
    state_file = SOURCE_ROOT / "profiles/dev/data/dealwatch_state.json"
    try:
        test_state = {
            "last_seen": {"test_search": "item123"},
            "last_run": datetime.now(timezone.utc).isoformat()
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(test_state, indent=2), encoding="utf-8")
        print_pass("State file written")
        report.record_pass()
        loaded_state = json.loads(state_file.read_text("utf-8"))
        if loaded_state == test_state:
            print_pass("State file read back correctly")
            report.record_pass()
        else:
            print_fail("State data mismatch")
            report.record_fail()
    except Exception as e:
        print_fail(f"State persistence test failed: {e}")
        report.record_fail()

def test_logging():
    print_header("TEST 10: Logging Functionality")
    log_file = SOURCE_ROOT / "logs/dealwatch.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        test_entry = f"{datetime.now(timezone.utc).isoformat()} | TEST | [vinyl] £15.00 (25.0%) on £40.00 | Test Item | https://ebay.co.uk/test\n"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(test_entry)
        print_pass("Log entry written")
        report.record_pass()
        if log_file.exists() and log_file.stat().st_size > 0:
            print_pass("Log file verified")
            report.record_pass()
        else:
            print_fail("Log file empty")
            report.record_fail()
    except Exception as e:
        print_fail(f"Logging test failed: {e}")
        report.record_fail()

def main():
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          DEAL HUNTER VALIDATION SUITE                      ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"Working directory: {SOURCE_ROOT}")
    print(Colors.END)
    start_time = time.time()
    test_file_structure()
    cfg = test_config()
    test_yaml_parsing()
    dc = test_discogs_api(cfg)
    es = test_ebay_api(cfg)
    test_profit_calculation()
    test_format_detection()
    test_exclude_filtering()
    test_state_persistence()
    test_logging()
    elapsed = time.time() - start_time
    report.print_summary()
    print(f"\nCompleted in {elapsed:.2f} seconds")
    sys.exit(0 if report.tests_failed == 0 else 1)

if __name__ == "__main__":
    main()
