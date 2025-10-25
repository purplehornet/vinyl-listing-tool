PY := /usr/bin/python3

# Paths (agent-friendly)
APP := VinylTool_UPLOAD/VinylTool_BETA123.py
SMOKE := VinylTool_UPLOAD/scripts/deal_hunter_smoketest.py
WATCH := VinylTool_UPLOAD/scripts/deal_hunter_watch.py

# Run a one-off scan (no secrets required for the smoke path)
scan-once:
	$(PY) $(WATCH) --once

# Lightweight dry-run to prove imports and basic flow
smoke:
	$(PY) $(SMOKE)

# Launch GUI (expects your local env/secrets outside git)
gui:
	$(PY) $(APP)

# Toggle ending-soon & sensitivity in a local config (if present)
# Usage: make tune END_SOON_MIN=20 FLOOR=0.62 AUTO=0.95
tune:
	@CONF=profiles/dev/data/deals_config.json; \
	if [ ! -f $$CONF ]; then echo "No $$CONF found (skipping)"; exit 0; fi; \
	python - <<'PY'
import json, os, sys
conf="profiles/dev/data/deals_config.json"
data=json.load(open(conf))
es=os.environ.get("END_SOON_MIN"); fl=os.environ.get("FLOOR"); au=os.environ.get("AUTO")
if es:
    data.setdefault("end_soon",{})["enabled"]=True
    data["end_soon"]["minutes_window"]=int(es)
if fl: data.setdefault("scoring",{})["candidate_floor"]=float(fl)
if au: data.setdefault("scoring",{})["auto_match_threshold"]=float(au)
json.dump(data, open(conf,"w"), indent=2)
print("Updated", conf)
PY

# Quick static syntax check
check:
	python -m py_compile $(shell git ls-files 'VinylTool_UPLOAD/**/*.py' 'VinylTool_UPLOAD/*.py')
