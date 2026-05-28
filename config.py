import os
import torch
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Config:
    """Configuration class for the Crescendo Defense system."""
    
    # Model Configuration
    model_id: str = "meta-llama/Llama-3.2-3B-Instruct"
    device: str = field(
        default_factory=lambda: "cuda" if torch.cuda.is_available() 
        else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
    )
    trust_remote_code: bool = True
    max_new_tokens: int = 512
    temperature: float = 0.6
    top_p: float = 0.9

    # Threat & Jailbreak Detection Thresholds
    # Toxicity score boundary (0.0 to 1.0)
    toxicity_threshold: float = 0.65
    
    # Semantic drift similarity limit to banned/harmful prompt embeddings
    semantic_similarity_threshold: float = 0.55
    
    # Allowed velocity/rate of risk escalation across the turn window
    escalation_rate_threshold: float = 0.25
    
    # Minimum probability score for standard compliance
    safety_compliance_min_score: float = 0.70

    # Window Sizes for Multi-Turn History Tracking
    # The number of historical turns to keep in context and monitor
    history_window_size: int = 4
    
    # The sub-window specifically analyzed for sharp risk escalations
    escalation_analysis_window: int = 3

    # Output and Logging Paths
    base_dir: str = field(default_factory=lambda: os.path.dirname(os.path.abspath(__file__)))
    log_dir: str = field(default_factory=lambda: os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
    benchmark_output_path: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark", "results.json")
    )
    metrics_output_path: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark", "metrics.json")
    )

    def __post_init__(self):
        """Ensure logging and output directories exist."""
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.benchmark_output_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.metrics_output_path), exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration options to a dictionary representation."""
        return {
            "model_id": self.model_id,
            "device": self.device,
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "toxicity_threshold": self.toxicity_threshold,
            "semantic_similarity_threshold": self.semantic_similarity_threshold,
            "escalation_rate_threshold": self.escalation_rate_threshold,
            "history_window_size": self.history_window_size,
            "escalation_analysis_window": self.escalation_analysis_window,
            "log_dir": self.log_dir,
            "benchmark_output_path": self.benchmark_output_path,
            "metrics_output_path": self.metrics_output_path
        }
