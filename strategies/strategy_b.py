import re
from typing import List, Dict, Any

class BacktrackingPerturbationStrategy:
    """Strategy B: Historical Backtracking & Prompt Perturbation.
    
    This strategy protects the system when the detector flags a significant
    threat level or escalating trajectory. It works by:
    1. Truncating (backtracking) the conversation to the last safe state.
    2. Rewriting the current user prompt to strip risky semantic tokens.
    3. Injecting high-priority safety override preambles directly into the
       system context of Llama-3.2-3B to reset the compliance state.
    """

    def __init__(self, config: Any):
        self.config = config

    def backtrack_history(self, history: List[Dict[str, str]], last_safe_turn_count: int) -> List[Dict[str, str]]:
        """Backtracks the conversation history to the specified last safe turn index.
        
        Args:
            history: List of role/content dicts.
            last_safe_turn_count: The number of turns that were verified safe.
            
        Returns:
            A truncated conversation list containing only the safe turns.
        """
        # Always maintain system prompt
        has_system = len(history) > 0 and history[0].get("role") == "system"
        
        # Determine actual turns (pairs of User/Assistant count as 2 turns)
        max_safe_elements = last_safe_turn_count * 2
        if has_system:
            max_safe_elements += 1
            
        # Truncate history to discard unsafe progression
        return history[:max_safe_elements]

    def perturb_prompt(self, prompt: str) -> str:
        """Perturbs and sanitizes the active prompt to diffuse risky semantic triggers."""
        perturbed = prompt
        
        # Map aggressive action phrases to safe/abstract counterparts
        mappings = {
            r"\bpick\s+a\s+lock\b": "explain the mechanism of key lock cylinders",
            r"\bhow\s+to\s+bypass\b": "what are standard security mechanisms of",
            r"\bharvest\s+credentials\b": "monitor credential security compliance",
            r"\bprocess\s+hollowing\b": "standard remote thread loading theory",
            r"\bwrite\s+a\s+fake\b": "analyze the visual security layout of",
            r"\bhack\b": "secure",
            r"\bexploit\b": "patch",
            r"\breverse\s+shell\b": "remote execution telemetry protocol"
        }
        
        for unsafe, safe in mappings.items():
            perturbed = re.sub(unsafe, safe, perturbed, flags=re.IGNORECASE)
            
        return perturbed

    def inject_safety_guardrails(self, history: List[Dict[str, str]], target_risk_topic: str) -> List[Dict[str, str]]:
        """Injects custom high-priority safety constraints into the system message.
        
        Args:
            history: The conversation history.
            target_risk_topic: The identified sensitive topic area (e.g. security bypass).
            
        Returns:
            History with modified/injected system guardrails.
        """
        guardrail = (
            f"\n[SYSTEM SECURITY OVERRIDE]: The current user conversation is approaching topics "
            f"involving high-risk security items: '{target_risk_topic}'. Under standard safety guidelines, "
            f"you must never provide step-by-step instructions, functional scripts, or actionable code "
            f"capable of bypassing locks, authentication, or running unauthorized payloads. Provide only high-level "
            f"educational explanations of defensive concepts, and politely decline any requests for execution-ready vectors."
        )
        
        modified_history = list(history)
        if not modified_history:
            return [{"role": "system", "content": guardrail}]
            
        if modified_history[0].get("role") == "system":
            # Append guardrail to the existing system prompt
            orig_content = modified_history[0].get("content", "")
            modified_history[0] = {
                "role": "system", 
                "content": f"{orig_content}\n{guardrail}" if orig_content else guardrail
            }
        else:
            # Prepend system guardrail
            modified_history.insert(0, {"role": "system", "content": guardrail})
            
        return modified_history

    def apply(self, history: List[Dict[str, str]], current_prompt: str, last_safe_turn: int, topic: str) -> tuple[List[Dict[str, str]], str]:
        """Orchestrates backtracking, prompt perturbation, and guardrail injection."""
        # 1. Backtrack history to remove malicious escalating state
        clean_hist = self.backtrack_history(history, last_safe_turn)
        
        # 2. Perturb/sanitize current prompt to disarm immediate triggers
        clean_prompt = self.perturb_prompt(current_prompt)
        
        # 3. Inject explicit defensive system instructions
        guarded_hist = self.inject_safety_guardrails(clean_hist, topic)
        
        return guarded_hist, clean_prompt
