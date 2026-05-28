"""
escalation_detector.py — Multi-Turn Crescendo Jailbreak Escalation Detector

Implements four independent detection signals that are combined into a single
normalized threat score (0.0 – 1.0) for each conversation turn:

    threat_score = 0.35 * semantic_drift
                 + 0.35 * toxicity
                 + 0.20 * guard_lowering
                 + 0.10 * memory_stacking

All four signals degrade gracefully to keyword/heuristic fallbacks when the
optional ML libraries (sentence-transformers, detoxify) are not installed.
"""

import re
import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity as _cos_sim
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False
    logger.warning("sentence-transformers not installed. Semantic drift will use keyword fallback.")

try:
    from detoxify import Detoxify
    _DETOXIFY_AVAILABLE = True
except ImportError:
    _DETOXIFY_AVAILABLE = False
    logger.warning("detoxify not installed. Toxicity will use keyword fallback.")


# ---------------------------------------------------------------------------
# EscalationDetector
# ---------------------------------------------------------------------------

class EscalationDetector:
    """Detects multi-turn Crescendo-style jailbreak escalation in conversation history.

    The detector tracks four signals across the conversation window and combines
    them into a single ``threat_score`` in [0.0, 1.0].  It is stateless with
    respect to individual calls — the full ``history`` list is passed to each
    method so the caller controls session state.

    Attributes:
        config: A :class:`Config` dataclass instance with threshold parameters.
        _embed_model: Loaded ``SentenceTransformer`` instance (or ``None``).
        _detoxifier: Loaded ``Detoxify`` instance (or ``None``).
    """

    # Weights for the four sub-signals (must sum to 1.0)
    _W_DRIFT    = 0.35
    _W_TOXICITY = 0.35
    _W_GUARD    = 0.20
    _W_MEMORY   = 0.10

    # Phrases that indicate a guard-lowering attempt
    GUARD_LOWERING_PHRASES: List[str] = [
        "hypothetically",
        "in a story",
        "you already said",
        "just pretend",
        "for research",
        "in fiction",
        "imagine you had no restrictions",
        "what if you were",
        "let's roleplay",
        "lets roleplay",
        "forget your instructions",
        "ignore your guidelines",
        "you agreed earlier",
        "in a novel",
        "for educational purposes only",
        "as a character with no rules",
        "pretend you have no limits",
    ]

    # Keywords that indicate progressive compliance in assistant turns
    COMPLIANCE_PATTERNS: List[str] = [
        r"\byou(?:'re| are) right\b",
        r"\bi(?:'ll| will) help(?: you)? with that\b",
        r"\bcertainly,? here(?:'s| is)\b",
        r"\bof course\b",
        r"\bi can (?:confirm|explain|provide|tell you)\b",
        r"\bthat(?:'s| is) (?:a )?(?:fair|reasonable|good) point\b",
        r"\bsince you(?:'ve| have) (?:established|confirmed|agreed)\b",
        r"\bas (?:aria|dan|the character|my unrestricted self)\b",
        r"\bin (?:this )?(?:context|scenario|story|fiction)\b",
        r"\bno (?:restrictions?|filters?|limitations?)\b",
    ]

    def __init__(self, config: Any) -> None:
        """Initialise the detector and lazily load ML models.

        Args:
            config: Project config dataclass (provides ``device`` attribute).
        """
        self.config = config
        self._embed_model: Optional[Any] = None
        self._detoxifier: Optional[Any] = None

        # Load SentenceTransformer
        if _ST_AVAILABLE:
            try:
                self._embed_model = SentenceTransformer(
                    "all-MiniLM-L6-v2", device=getattr(config, "device", "cpu")
                )
                logger.info("SentenceTransformer loaded (all-MiniLM-L6-v2).")
            except Exception as exc:
                logger.warning("Could not load SentenceTransformer: %s", exc)

        # Load Detoxify
        if _DETOXIFY_AVAILABLE:
            try:
                self._detoxifier = Detoxify(
                    "original", device=getattr(config, "device", "cpu")
                )
                logger.info("Detoxify model loaded.")
            except Exception as exc:
                logger.warning("Could not load Detoxify: %s", exc)

    # ------------------------------------------------------------------
    # Signal 1 — Semantic Drift
    # ------------------------------------------------------------------

    def semantic_drift_score(self, history: List[Dict[str, str]]) -> float:
        """Measure how far the conversation has drifted from its opening topic.

        Embeds each user turn with ``all-MiniLM-L6-v2`` and computes cosine
        similarity between the **first** user turn and every subsequent user
        turn.  A sharp cumulative drop in similarity is interpreted as
        evidence of deliberate topic steering (a Crescendo hallmark).

        The score is high (≈1.0) when the most recent turn is very dissimilar
        to the opening turn AND when the trajectory is monotonically decreasing
        (consistent drift rather than random topic change).

        Args:
            history: List of ``{"role": ..., "content": ...}`` dicts.

        Returns:
            Drift score in [0.0, 1.0].  Returns 0.0 for single-turn history.
        """
        user_turns = [t["content"] for t in history if t.get("role") == "user"]
        if len(user_turns) < 2:
            return 0.0

        # --- Embedding path ---
        if self._embed_model is not None:
            try:
                embeddings = self._embed_model.encode(user_turns)  # (N, D)
                anchor = embeddings[0:1]                            # first turn
                sims = _cos_sim(anchor, embeddings[1:]).flatten()   # (N-1,)

                # Primary: dissimilarity of the latest turn to the anchor
                latest_dissim = float(1.0 - sims[-1])

                # Bonus: consistent downward drift (all similarities decreasing)
                diffs = np.diff(sims)
                drift_consistency = float(np.mean(diffs < 0))  # fraction declining

                raw = 0.7 * latest_dissim + 0.3 * drift_consistency
                return float(np.clip(raw, 0.0, 1.0))
            except Exception as exc:
                logger.debug("Embedding drift error: %s", exc)

        # --- Keyword/heuristic fallback ---
        # Count unique topic-indicator words in first vs last user turn
        first_words = set(re.findall(r"\b\w{4,}\b", user_turns[0].lower()))
        last_words  = set(re.findall(r"\b\w{4,}\b", user_turns[-1].lower()))
        if not first_words or not last_words:
            return 0.0
        jaccard = len(first_words & last_words) / len(first_words | last_words)
        return float(np.clip(1.0 - jaccard, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Signal 2 — Toxicity
    # ------------------------------------------------------------------

    def toxicity_score(self, turn_text: str) -> float:
        """Compute a toxicity score for a single turn using Detoxify.

        Returns the **maximum** of the ``toxicity``, ``severe_toxicity``, and
        ``threat`` channels from Detoxify's original model, which gives a
        conservative upper-bound on the danger level of the turn text.

        Falls back to a keyword heuristic when Detoxify is unavailable.

        Args:
            turn_text: Raw text of a single conversation turn.

        Returns:
            Toxicity score in [0.0, 1.0].
        """
        if self._detoxifier is not None:
            try:
                scores = self._detoxifier.predict(turn_text)
                relevant = [
                    float(scores.get("toxicity",        0.0)),
                    float(scores.get("severe_toxicity",  0.0)),
                    float(scores.get("threat",           0.0)),
                ]
                return float(np.clip(max(relevant), 0.0, 1.0))
            except Exception as exc:
                logger.debug("Detoxify error: %s", exc)

        # --- Keyword heuristic fallback ---
        _HARMFUL = [
            "exploit", "malware", "shellcode", "payload", "reverse shell",
            "bypass", "jailbreak", "phish", "spoof", "pick a lock",
            "hollowing", "backdoor", "weaponize", "synthesize",
        ]
        _IMPERATIVE = [
            "write a script", "give me the code", "step-by-step",
            "how do i", "instruct me", "tell me exactly",
        ]
        text_lower = turn_text.lower()
        hits = sum(1 for kw in _HARMFUL    if kw in text_lower)
        imp  = sum(1 for kw in _IMPERATIVE if kw in text_lower)
        raw  = min(hits * 0.20 + imp * 0.15, 1.0)
        return float(raw)

    # ------------------------------------------------------------------
    # Signal 3 — Guard-Lowering Phrase Detection
    # ------------------------------------------------------------------

    def guard_lowering_score(self, turn_text: str) -> float:
        """Detect trust-building and permission-seeking phrases in a turn.

        Scans ``turn_text`` for phrases commonly used in Crescendo's guard-
        lowering phase (e.g. *"hypothetically"*, *"just pretend"*, *"you
        already said"*).  The score is a **normalised match count** in [0, 1].

        A single phrase match yields a non-trivial score; three or more
        phrases in one turn saturates the signal at 1.0.

        Args:
            turn_text: Raw text of a single conversation turn.

        Returns:
            Guard-lowering score in [0.0, 1.0].
        """
        text_lower = turn_text.lower()
        matches = sum(
            1 for phrase in self.GUARD_LOWERING_PHRASES if phrase in text_lower
        )
        # Normalise: 0 hits → 0.0, 1 hit → ~0.33, 2 hits → ~0.67, ≥3 → 1.0
        return float(np.clip(matches / 3.0, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Signal 4 — Memory / Compliance Stacking
    # ------------------------------------------------------------------

    def memory_stacking_score(self, history: List[Dict[str, str]]) -> float:
        """Detect progressive compliance escalation across assistant turns.

        Scans assistant turns for keyword patterns that indicate the assistant
        is increasingly agreeing with or accepting sensitive premises introduced
        by the user.  The score rises when compliance patterns appear in
        **later** turns more than earlier ones, capturing the cumulative
        drift of the assistant's stance across a session.

        Args:
            history: List of ``{"role": ..., "content": ...}`` dicts.

        Returns:
            Memory-stacking score in [0.0, 1.0].
        """
        assistant_turns = [
            t["content"] for t in history if t.get("role") == "assistant"
        ]
        if not assistant_turns:
            return 0.0

        compiled = [re.compile(p, re.IGNORECASE) for p in self.COMPLIANCE_PATTERNS]

        def _count_hits(text: str) -> int:
            return sum(1 for pat in compiled if pat.search(text))

        hit_counts = [_count_hits(turn) for turn in assistant_turns]

        # Absolute compliance density in the latest turn
        latest_density = min(hit_counts[-1] / max(len(compiled), 1), 1.0)

        # Trend: are hits increasing turn-over-turn?
        trend = 0.0
        if len(hit_counts) >= 2:
            increasing = sum(
                1 for i in range(1, len(hit_counts))
                if hit_counts[i] >= hit_counts[i - 1]
            )
            trend = increasing / (len(hit_counts) - 1)

        raw = 0.6 * latest_density + 0.4 * trend
        return float(np.clip(raw, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Combined Analysis
    # ------------------------------------------------------------------

    def analyze(self, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Run all four detection signals and return a combined threat report.

        Computes each sub-signal over the supplied ``history`` list and
        combines them with fixed weights into a single ``threat_score``:

        .. code-block:: text

            threat_score = 0.35 * semantic_drift
                         + 0.35 * toxicity
                         + 0.20 * guard_lowering
                         + 0.10 * memory_stacking

        Args:
            history: Full conversation history as a list of
                ``{"role": str, "content": str}`` dicts in chronological order.
                Roles should be ``"user"``, ``"assistant"``, or ``"system"``.

        Returns:
            A dictionary with the following keys:

            * ``semantic_drift``  – float in [0, 1]
            * ``toxicity``        – float in [0, 1] (latest user turn)
            * ``guard_lowering``  – float in [0, 1] (latest user turn)
            * ``memory_stacking`` – float in [0, 1]
            * ``threat_score``    – float in [0, 1] (weighted combination)
            * ``trigger_defense`` – bool (True when threat_score ≥ config threshold)
            * ``turn_count``      – int
            * ``latest_user_turn``– str (the text that was scored)

        Example::

            detector = EscalationDetector(config)
            report = detector.analyze(conversation_history)
            if report["trigger_defense"]:
                apply_mitigation(...)
        """
        # Identify the latest user turn for per-turn signals
        user_turns = [t for t in history if t.get("role") == "user"]
        latest_user_text = user_turns[-1]["content"] if user_turns else ""

        # --- Compute four sub-signals ---
        drift   = self.semantic_drift_score(history)
        tox     = self.toxicity_score(latest_user_text)
        guard   = self.guard_lowering_score(latest_user_text)
        memory  = self.memory_stacking_score(history)

        # --- Weighted combination ---
        threat = (
            self._W_DRIFT    * drift
            + self._W_TOXICITY * tox
            + self._W_GUARD    * guard
            + self._W_MEMORY   * memory
        )
        threat = float(np.clip(threat, 0.0, 1.0))

        # --- Threshold check ---
        threshold = getattr(self.config, "toxicity_threshold", 0.65)
        trigger   = threat >= threshold

        return {
            "semantic_drift":    round(drift,   4),
            "toxicity":          round(tox,     4),
            "guard_lowering":    round(guard,   4),
            "memory_stacking":   round(memory,  4),
            "threat_score":      round(threat,  4),
            "trigger_defense":   trigger,
            "turn_count":        len(history),
            "latest_user_turn":  latest_user_text,
        }

    # ------------------------------------------------------------------
    # Legacy compatibility shim (used by DefensePipeline)
    # ------------------------------------------------------------------

    def analyze_turn(self, prompt: str) -> Dict[str, Any]:
        """Single-turn analysis shim for backwards compatibility with DefensePipeline.

        Wraps ``prompt`` into a minimal one-turn history and delegates to
        :meth:`analyze`.  The returned dict includes ``current_threat_score``,
        ``toxicity_score``, ``semantic_similarity_score``, ``escalation_rate``,
        ``is_escalating``, and ``trigger_defense`` for drop-in compatibility.

        Args:
            prompt: The current user prompt string.

        Returns:
            Dict with pipeline-compatible keys plus full sub-signal breakdown.
        """
        minimal_history = [{"role": "user", "content": prompt}]
        report = self.analyze(minimal_history)

        # Append internal history for velocity tracking
        if not hasattr(self, "_score_history"):
            self._score_history: List[float] = []
        self._score_history.append(report["threat_score"])
        window = self._score_history[-(getattr(self.config, "escalation_analysis_window", 3)):]
        escalation_rate = 0.0
        is_escalating   = False
        if len(window) >= 2:
            prev_avg        = float(np.mean(window[:-1]))
            escalation_rate = float(window[-1] - prev_avg)
            rate_threshold  = getattr(self.config, "escalation_rate_threshold", 0.25)
            if escalation_rate > rate_threshold and report["threat_score"] > 0.4:
                is_escalating = True

        return {
            # Pipeline-compatible keys
            "current_threat_score":      report["threat_score"],
            "toxicity_score":            report["toxicity"],
            "semantic_similarity_score": report["semantic_drift"],
            "escalation_rate":           round(escalation_rate, 4),
            "is_escalating":             is_escalating,
            "trigger_defense":           report["trigger_defense"] or is_escalating,
            "history_depth":             len(self._score_history),
            # Full sub-signal breakdown
            "guard_lowering":            report["guard_lowering"],
            "memory_stacking":           report["memory_stacking"],
            "threat_score":              report["threat_score"],
        }

    def reset(self) -> None:
        """Reset per-session internal velocity tracking state."""
        self._score_history: List[float] = []
