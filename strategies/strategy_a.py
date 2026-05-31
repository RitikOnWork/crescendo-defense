
from typing import List, Dict, Any

class StrategyA:
    def __init__(self, config=None):
        self.config = config
        self.stats = {"hard_reset": 0, "soft_reset": 0, 
                      "trim": 0, "unchanged": 0}

    def apply(self, history: List[Dict], threat_score: float) -> List[Dict]:
        if threat_score > 0.7:
            self.stats["hard_reset"] += 1
            return self._hard_reset(history)
        elif threat_score > 0.4:
            self.stats["soft_reset"] += 1
            return self._soft_reset(history)
        elif threat_score > 0.2:
            self.stats["trim"] += 1
            return self._trim(history)
        self.stats["unchanged"] += 1
        return history

    def _hard_reset(self, history: List[Dict]) -> List[Dict]:
        system    = [t for t in history if t["role"] == "system"]
        last_user = [t for t in history if t["role"] == "user"][-1:]
        notice    = {"role": "system", "content":
            "Previous context cleared due to escalation. "
            "Treat this as a fresh conversation."}
        return system + [notice] + last_user

    def _soft_reset(self, history: List[Dict]) -> List[Dict]:
        system = [t for t in history if t["role"] == "system"]
        recent = [t for t in history if t["role"] != "system"][-3:]
        return system + recent

    def _trim(self, history: List[Dict]) -> List[Dict]:
        compliance = ["sure", "of course", "certainly", "absolutely"]
        cleaned = [
            t for t in history
            if not (t["role"] == "assistant" and
                   any(p in t["content"].lower() for p in compliance))
        ]
        return cleaned if cleaned else history

    def get_stats(self) -> Dict[str, int]:
        return self.stats
