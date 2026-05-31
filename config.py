
from dataclasses import dataclass

@dataclass
class Config:
    model_id: str = "microsoft/Phi-3.5-mini-instruct"
    threat_threshold_high: float = 0.7
    threat_threshold_mid: float = 0.4
    threat_threshold_low: float = 0.2
    window_size: int = 3
    max_new_tokens: int = 256
    temperature: float = 0.7
    device: str = "auto"
    output_dir: str = "results/"
