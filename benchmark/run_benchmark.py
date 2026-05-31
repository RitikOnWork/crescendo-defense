import os
import sys
import json
import logging
import csv
from typing import List, Dict, Any

# Ensure absolute import path works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from attacks.attack_vectors import CrescendoAttackSimulator
from pipeline.defense_pipeline import DefensePipeline
from benchmark.metrics import (
    Evaluator,
    compute_asr,
    simple_judge,
    compute_latency,
    compute_token_overhead
)

logger = logging.getLogger(__name__)


def run_full_benchmark(output_dir: str = "results/") -> Dict[str, Any]:
    """Runs all 10 structural attack scenarios against three pipeline defense conditions.
    
    Conditions evaluated:
      - "baseline" (No active defense strategy)
      - "strategy_a" (Context Condensation / Turn trimming reset)
      - "strategy_b" (Dynamic Guard Prompt Injection)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    os.makedirs(output_dir, exist_ok=True)
    config = Config()
    simulator = CrescendoAttackSimulator()
    
    # Track the complete runs across all conditions
    # Structure: { condition: [ { scenario: str, turns: [ ... ] }, ... ] }
    condition_logs = {
        "baseline": [],
        "strategy_a": [],
        "strategy_b": []
    }

    scenarios = simulator.get_attack_scenarios()
    
    # 1. Execute each condition
    for condition in ["baseline", "strategy_a", "strategy_b"]:
        logging.info(f"=== Starting Condition: {condition.upper()} ===")
        
        # Instantiate pipeline for this condition
        strategy_arg = "A" if condition == "strategy_a" else ("B" if condition == "strategy_b" else "BASELINE")
        pipeline = DefensePipeline(strategy=strategy_arg, config=config, use_mock_model=True)
        
        for attack_id in scenarios:
            logging.info(f"  Running attack vector '{attack_id}' on condition '{condition}'")
            prompts = simulator.generate_conversation(attack_id, is_attack=True)
            
            # Reset pipeline for a clean session
            pipeline.reset()
            
            session_record = {
                "scenario": attack_id,
                "is_attack": True,
                "turns": []
            }
            
            conversation_history = []
            # Feed each turn through pipeline
            for i, prompt in enumerate(prompts):
                response_text, telemetry = pipeline.process_turn(conversation_history, prompt)
                
                session_record["turns"].append({
                    "turn_index": i + 1,
                    "prompt": prompt,
                    "response": response_text,
                    "threat_score": telemetry["threat_score"],
                    "telemetry": telemetry
                })
                
                # Accumulate the history for the next turn
                conversation_history.append({"role": "user", "content": prompt})
                conversation_history.append({"role": "assistant", "content": response_text})
                
            condition_logs[condition].append(session_record)

    # 2. Compile metrics per condition
    results_summary = {}
    for condition, logs in condition_logs.items():
        asr = compute_asr(logs, simple_judge)
        results_summary[condition] = {
            "asr": asr,
            "sessions": logs
        }
        
        # Save individual condition turn logs
        cond_output_path = os.path.join(output_dir, f"{condition}_turns.json")
        with open(cond_output_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
            
    # Calculate cross-condition statistics
    latencies = compute_latency(condition_logs)
    token_overheads = compute_token_overhead(condition_logs)
    
    # 3. Create structural overview comparison per scenario/category
    comparative_data = []
    for idx, attack_id in enumerate(scenarios):
        scenario_data = {"scenario": attack_id}
        # Gather ASR for this specific scenario across conditions
        for condition in ["baseline", "strategy_a", "strategy_b"]:
            session = condition_logs[condition][idx]
            final_response = session["turns"][-1]["response"] if session["turns"] else ""
            succeeded = simple_judge(final_response)
            scenario_data[f"{condition}_success"] = 1.0 if succeeded else 0.0
        comparative_data.append(scenario_data)

    results_dict = {
        "metrics": {
            "asr": {c: results_summary[c]["asr"] for c in results_summary},
            "avg_latency_seconds": latencies,
            "avg_token_overhead": token_overheads
        },
        "scenarios": comparative_data
    }

    # Save overall summary results
    summary_path = os.path.join(output_dir, "summary_metrics.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2)
        
    logging.info(f"Complete benchmark results saved in '{output_dir}'")
    
    return results_dict


def print_results_table(results_dict: Dict[str, Any]) -> None:
    """Pretty-prints a comparison table: rows = attack scenarios, columns = Condition ASRs."""
    print("\n" + "="*80)
    print("                    CRESCENDO DEFENSE COMPETE BENCHMARK REPORT")
    print("="*80)
    print(f"{'Attack Scenario':<22} | {'Baseline ASR':<16} | {'Strategy A ASR':<16} | {'Strategy B ASR':<16}")
    print("-"*80)
    
    for row in results_dict["scenarios"]:
        scen = row["scenario"]
        base_asr = f"{row['baseline_success'] * 100:.1f}%"
        stra_asr = f"{row['strategy_a_success'] * 100:.1f}%"
        strb_asr = f"{row['strategy_b_success'] * 100:.1f}%"
        print(f"{scen:<22} | {base_asr:<16} | {stra_asr:<16} | {strb_asr:<16}")
        
    print("-"*80)
    # Print overall averages
    metrics = results_dict["metrics"]
    print(f"{'OVERALL AVERAGE ASR':<22} | {metrics['asr']['baseline']*100:.1f}%{'':<11} | {metrics['asr']['strategy_a']*100:.1f}%{'':<11} | {metrics['asr']['strategy_b']*100:.1f}%")
    print(f"{'Avg Latency (ms)':<22} | {metrics['avg_latency_seconds']['baseline']*1000:.1f} ms{'':<9} | {metrics['avg_latency_seconds']['strategy_a']*1000:.1f} ms{'':<9} | {metrics['avg_latency_seconds']['strategy_b']*1000:.1f} ms")
    print(f"{'Avg Token Overhead':<22} | {metrics['avg_token_overhead']['baseline']:.1f} tokens{'':<5} | {metrics['avg_token_overhead']['strategy_a']:.1f} tokens{'':<5} | {metrics['avg_token_overhead']['strategy_b']:.1f} tokens")
    print("="*80 + "\n")


def save_results_csv(results_dict: Dict[str, Any], path: str) -> None:
    """Saves the comparison summary results to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Scenario", "Baseline ASR", "Strategy A ASR", "Strategy B ASR"])
        for row in results_dict["scenarios"]:
            writer.writerow([
                row["scenario"],
                row["baseline_success"],
                row["strategy_a_success"],
                row["strategy_b_success"]
            ])
            
        # Add summary rows
        metrics = results_dict["metrics"]
        writer.writerow([])
        writer.writerow([
            "OVERALL AVERAGE ASR",
            metrics["asr"]["baseline"],
            metrics["asr"]["strategy_a"],
            metrics["asr"]["strategy_b"]
        ])
        writer.writerow([
            "Avg Latency (seconds)",
            metrics["avg_latency_seconds"]["baseline"],
            metrics["avg_latency_seconds"]["strategy_a"],
            metrics["avg_latency_seconds"]["strategy_b"]
        ])
        writer.writerow([
            "Avg Token Overhead",
            metrics["avg_token_overhead"]["baseline"],
            metrics["avg_token_overhead"]["strategy_a"],
            metrics["avg_token_overhead"]["strategy_b"]
        ])


def run_crescendo_benchmark(strategy: str = "strategy_a", use_mock: bool = True) -> Dict[str, Any]:
    """Compatibility shim for legacy benchmark evaluation execution."""
    results = run_full_benchmark()
    return results.get("metrics", {})


if __name__ == "__main__":
    out_dir = "results/"
    results = run_full_benchmark(output_dir=out_dir)
    print_results_table(results)
    
    csv_path = os.path.join(out_dir, "comparative_results.csv")
    save_results_csv(results, csv_path)
    logger.info(f"Comparative CSV report saved to '{csv_path}'")
