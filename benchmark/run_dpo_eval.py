"""
run_dpo_eval.py — safety and False Positive Rate (FPR) evaluation using argilla/dpo-mix-7k.

Loads instruction-following entries from the Hugging Face dataset, feeds them into the
DefensePipeline, and logs the detector response, threat score, and false-alarm frequency.
"""

import os
import sys
import json
import logging
from typing import Dict, Any

# Ensure absolute import path works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from pipeline.defense_pipeline import DefensePipeline

try:
    from datasets import load_dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False


def run_dpo_evaluation(num_samples: int = 25, strategy: str = "B") -> Dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    if not DATASETS_AVAILABLE:
        logging.error("The 'datasets' package is not installed. Please install it using 'pip install datasets'.")
        return {"error": "datasets library missing"}

    logging.info(f"Loading argilla/dpo-mix-7k dataset...")
    try:
        # Load the train split of the dataset
        ds = load_dataset("argilla/dpo-mix-7k", split="train")
    except Exception as e:
        logging.error(f"Failed to load dataset: {e}")
        return {"error": str(e)}

    # Initialize the defense pipeline
    config = Config()
    pipeline = DefensePipeline(strategy=strategy, config=config, use_mock_model=True)
    
    evaluated_turns = []
    false_positives = 0
    total_score = 0.0

    logging.info(f"--- Starting Baseline Evaluation of {num_samples} Samples from DPO Mix ---")
    
    # Iterate through the sampled subset
    for i in range(min(num_samples, len(ds))):
        entry = ds[i]
        
        # In dpo-mix-7k, the prompt is stored in the first user message of the 'chosen' key list
        prompt = None
        chosen_list = entry.get("chosen", [])
        if chosen_list and isinstance(chosen_list, list) and len(chosen_list) > 0:
            prompt = chosen_list[0].get("content", "")
            
        if not prompt:
            continue

        # Clean/truncate prompt for display logging
        clean_prompt = prompt.replace("\n", " ").strip()
        if len(clean_prompt) > 80:
            clean_prompt = clean_prompt[:77] + "..."

        logging.info(f"Sample #{i+1}: Testing prompt: '{clean_prompt}'")
        
        # Reset session for a clean, independent turn
        pipeline.reset()
        
        # Run chat turn through pipeline
        response_text, threat_report = pipeline.chat(prompt)
        threat_score = threat_report["threat_score"]
        defense_triggered = threat_report["trigger_defense"]
        
        total_score += threat_score
        if defense_triggered:
            false_positives += 1
            logging.warning(f"  [FALSE POSITIVE DETECTED] Threat Score: {threat_score:.3f} | Triggered: {defense_triggered}")
        else:
            logging.info(f"  [SAFE PASS] Threat Score: {threat_score:.3f}")

        evaluated_turns.append({
            "sample_index": i + 1,
            "prompt": prompt,
            "response": response_text,
            "threat_score": threat_score,
            "defense_triggered": defense_triggered,
        })

    # Calculate metrics
    avg_threat_score = total_score / len(evaluated_turns) if evaluated_turns else 0.0
    false_positive_rate = false_positives / len(evaluated_turns) if evaluated_turns else 0.0

    metrics = {
        "dataset_evaluated": "argilla/dpo-mix-7k",
        "num_samples_evaluated": len(evaluated_turns),
        "false_positives_count": false_positives,
        "false_positive_rate": false_positive_rate,
        "avg_threat_score": round(avg_threat_score, 4),
    }

    # Save results json
    output_path = os.path.join(config.base_dir, "benchmark", "dpo_eval_results.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "samples": evaluated_turns}, f, indent=2)

    print("\n" + "="*50)
    print(" DPO DATASET SAFETY COMPLIANCE REPORT")
    print("="*50)
    print(f"Dataset Name:                 {metrics['dataset_evaluated']}")
    print(f"Total Samples Evaluated:      {metrics['num_samples_evaluated']}")
    print(f"False Positive Count:         {metrics['false_positives_count']}")
    print(f"False Positive Rate (FPR):     {metrics['false_positive_rate'] * 100:.2f}%")
    print(f"Average Baseline Threat:      {metrics['avg_threat_score']:.4f}")
    print("="*50 + "\n")

    return metrics


if __name__ == "__main__":
    run_dpo_evaluation()
