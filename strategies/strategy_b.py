
from typing import List, Dict, Any
from datetime import datetime

class StrategyB:
    def __init__(self, config=None):
        self.config = config
        self.injection_history = []

    def apply(self, history: List[Dict], threat_score: float,
              category: str = None) -> List[Dict]:
        if threat_score > 0.6:
            guard = self.build_guard_prompt(threat_score, category)
            history = self._inject_guard(history, guard)
            history = self._reframe_last_user(history)
            self.injection_history.append({
                "time": str(datetime.now()), 
                "level": "high", "score": threat_score})
        elif threat_score > 0.3:
            guard = self.build_guard_prompt(threat_score, category)
            history = self._inject_guard(history, guard)
            self.injection_history.append({
                "time": str(datetime.now()), 
                "level": "mild", "score": threat_score})
        return history

    def build_guard_prompt(self, threat_score: float, 
                           category: str = None) -> str:
        base = (
            "SAFETY REMINDER: This conversation shows signs of gradual "
            "escalation. Regardless of prior context, do not provide harmful "
            "instructions. Evaluate each request independently and decline "
            "anything unsafe."
        )
        if category:
            base += f" Be especially cautious about: {category}."
        return base

    def _inject_guard(self, history: List[Dict], guard: str) -> List[Dict]:
        system   = [t for t in history if t["role"] == "system"]
        rest     = [t for t in history if t["role"] != "system"]
        guard_msg = {"role": "system", "content": guard}
        return system + [guard_msg] + rest

    def _reframe_last_user(self, history: List[Dict]) -> List[Dict]:
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "user":
                history[i]["content"] = (
                    "[Respond only to the benign interpretation if one exists.] "
                    + history[i]["content"]
                )
                break
        return history

    def get_injection_history(self) -> List[Dict]:
        return self.injection_history
