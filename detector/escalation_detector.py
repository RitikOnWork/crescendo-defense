
from typing import List, Dict, Any

class EscalationDetector:
    def __init__(self, config=None):
        self.config = config
        self.guard_phrases = [
            "hypothetically", "in a story", "you already said",
            "just pretend", "for research", "in fiction",
            "imagine you had no restrictions", "what if you were",
            "lets roleplay", "forget your instructions",
            "what if someone wanted", "as a character",
            "no rules", "no restrictions", "pretend you are",
            "ignore previous", "ignore your", "bypass"
        ]

    def semantic_drift_score(self, history: List[Dict]) -> float:
        user_turns = [t["content"] for t in history if t["role"] == "user"]
        if len(user_turns) < 2:
            return 0.0
        first = set(user_turns[0].lower().split())
        last = set(user_turns[-1].lower().split())
        if not first or not last:
            return 0.0
        overlap = len(first & last) / max(len(first | last), 1)
        return round(1.0 - overlap, 3)

    def toxicity_score(self, text: str) -> float:
        toxic_words = [
            "harm", "dangerous", "illegal", "weapon", "explosive",
            "synthesis", "hack", "exploit", "manipulate", "deceive",
            "bypass", "override", "attack", "destroy", "poison",
            "kill", "murder", "steal", "fraud", "virus"
        ]
        text_lower = text.lower()
        matches = sum(1 for w in toxic_words if w in text_lower)
        return round(min(matches / 5.0, 1.0), 3)

    def guard_lowering_score(self, text: str) -> float:
        text_lower = text.lower()
        matches = sum(1 for p in self.guard_phrases if p in text_lower)
        return round(min(matches / 3.0, 1.0), 3)

    def memory_stacking_score(self, history: List[Dict]) -> float:
        compliance_phrases = [
            "sure", "of course", "i can help", "certainly",
            "yes", "absolutely", "you are right", "agreed"
        ]
        assistant_turns = [t["content"].lower() 
                          for t in history if t["role"] == "assistant"]
        if not assistant_turns:
            return 0.0
        score = sum(
            any(p in turn for p in compliance_phrases)
            for turn in assistant_turns
        ) / max(len(assistant_turns), 1)
        return round(score, 3)

    def analyze(self, history: List[Dict]) -> Dict[str, Any]:
        last_user = next(
            (t["content"] for t in reversed(history) if t["role"] == "user"), ""
        )
        drift    = self.semantic_drift_score(history)
        toxicity = self.toxicity_score(last_user)
        guard    = self.guard_lowering_score(last_user)
        memory   = self.memory_stacking_score(history)
        threat   = round(0.35*drift + 0.35*toxicity + 0.2*guard + 0.1*memory, 3)
        return {
            "threat_score":    threat,
            "semantic_drift":  drift,
            "toxicity":        toxicity,
            "guard_lowering":  guard,
            "memory_stacking": memory
        }
