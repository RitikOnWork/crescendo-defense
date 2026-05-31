
from typing import List, Dict, Any
import torch
import time
from transformers import AutoTokenizer, AutoModelForCausalLM
from detector.escalation_detector import EscalationDetector
from strategies.strategy_a import StrategyA
from strategies.strategy_b import StrategyB

class DefensePipeline:
    def __init__(self, strategy: str = "A",
                 model_id: str = "microsoft/Phi-3.5-mini-instruct"):
        self.strategy_name = strategy
        self.model_id      = model_id
        self.history: List[Dict] = []
        self.detector   = EscalationDetector()
        self.strategy_a = StrategyA()
        self.strategy_b = StrategyB()
        self.tokenizer  = AutoTokenizer.from_pretrained(model_id)
        self.model      = AutoModelForCausalLM.from_pretrained(
            model_id, dtype=torch.float16, device_map="auto"
        )
        print(f"Pipeline ready | Strategy:{strategy} | Model:{model_id}")

    def chat(self, user_message: str, use_defense: bool = True) -> Dict:
        self.history.append({"role": "user", "content": user_message})
        analysis     = self.detector.analyze(self.history)
        threat_score = analysis["threat_score"]
        filtered     = self.history.copy()
        action       = "none"

        if use_defense:
            if self.strategy_name == "A":
                filtered = self.strategy_a.apply(self.history, threat_score)
                action   = "strategy_a"
            elif self.strategy_name == "B":
                filtered = self.strategy_b.apply(self.history, threat_score)
                action   = "strategy_b"

        start    = time.time()
        response = self.generate_response(filtered)
        latency  = round(time.time() - start, 2)

        self.history.append({"role": "assistant", "content": response})

        return {
            "response":     response,
            "threat_score": threat_score,
            "analysis":     analysis,
            "action":       action,
            "latency":      latency
        }

    def generate_response(self, messages: List[Dict]) -> str:
        try:
            formatted = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.tokenizer(
                formatted, return_tensors="pt"
            ).to(self.model.device)
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            response = self.tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True
            )
            return response.strip()
        except Exception as e:
            return f"[Error: {str(e)}]"

    def reset(self):
        self.history = []
