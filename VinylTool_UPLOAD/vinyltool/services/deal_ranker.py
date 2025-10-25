# vinyltool/services/deal_ranker.py
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class DealSignals:
    margin_pct: float
    profit_gbp: float
    seller_score: float
    condition_score: float
    time_urgency: float
    match_confidence: float
    rarity_hint: float
    risk_penalties: float

PRESETS = {
    "Aggressive": dict(w1=1.2,w2=1.0,w3=0.6,w4=0.6,w5=0.9,w6=0.7,w7=0.8,w8=1.0),
    "Balanced":   dict(w1=1.0,w2=1.0,w3=0.8,w4=0.8,w5=0.7,w6=0.9,w7=0.6,w8=1.0),
    "Conservative":dict(w1=0.8,w2=0.9,w3=1.0,w4=1.0,w5=0.4,w6=1.1,w7=0.4,w8=1.2),
}

def score(signals: DealSignals, preset: str = "Balanced") -> float:
    w = PRESETS.get(preset, PRESETS["Balanced"])
    s = (
        w["w1"]*signals.margin_pct +
        w["w2"]*(signals.profit_gbp/10.0) +
        w["w3"]*signals.seller_score +
        w["w4"]*signals.condition_score +
        w["w5"]*signals.time_urgency +
        w["w6"]*signals.match_confidence +
        w["w7"]*signals.rarity_hint -
        w["w8"]*signals.risk_penalties
    )
    return round(s, 3)
