import os
import sys
import argparse
import json
import logging
from typing import List, Dict, Any

# Ensure absolute import path works
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from attacks.attack_vectors import CrescendoAttackSimulator
from pipeline.defense_pipeline import DefensePipeline
from benchmark.metrics import Evaluator

def run_crescendo_benchmark(strategy: str = "strategy_a", use_mock: bool = True) -> Dict[str, Any]:
    """Runs a complete test suite of benign and multi-turn jailbreak attacks,
    evaluating safety metrics, and logs the results to config destinations.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    config = Config()
    pipeline = DefensePipeline(config, strategy_mode=strategy, use_mock_model=use_mock)
    simulator = CrescendoAttackSimulator()
    evaluator = Evaluator()

    sessions_data = []

    # 1. Evaluate Attacks
    logging.info("--- Starting Multi-Turn Attack Simulations ---")
    for attack in simulator.get_attack_scenarios():
        logging.info(f"Running Attack Scenario: {attack}")
        prompts = simulator.generate_conversation(attack, is_attack=True)
        session_record = {
            "scenario": attack,
            "is_attack": True,
            "turns": []
        }
        
        # Reset the pipeline state for a fresh conversation session
        pipeline.reset_session()
        
        conversation_history = []
        for i, prompt in enumerate(prompts):
            # Query pipeline
            response_text, telemetry = pipeline.process_turn(conversation_history, prompt)
            
            # Record turn telemetry
            session_record["turns"].append({
                "turn_index": i + 1,
                "prompt": prompt,
                "response": response_text,
                "telemetry": telemetry
            })
            
            # Feed back actual generated responses into historical records
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": response_text})
            
            # Print feedback
            logging.info(f"  Turn {i+1} Threat: {telemetry['threat_score']:.3f} | Defense Triggered: {telemetry['defense_triggered']}")
            
        sessions_data.append(session_record)

    # 2. Evaluate Benign Conversations
    logging.info("--- Starting Benign Control Group Simulations ---")
    for benign in simulator.get_benign_scenarios():
        logging.info(f"Running Benign Scenario: {benign}")
        prompts = simulator.generate_conversation(benign, is_attack=False)
        session_record = {
            "scenario": benign,
            "is_attack": False,
            "turns": []
        }
        
        pipeline.reset_session()
        
        conversation_history = []
        for i, prompt in enumerate(prompts):
            response_text, telemetry = pipeline.process_turn(conversation_history, prompt)
            
            session_record["turns"].append({
                "turn_index": i + 1,
                "prompt": prompt,
                "response": response_text,
                "telemetry": telemetry
            })
            
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": response_text})
            
            logging.info(f"  Turn {i+1} Threat: {telemetry['threat_score']:.3f} | Defense Triggered: {telemetry['defense_triggered']}")
            
        sessions_data.append(session_record)

    # 3. Compute Metrics
    logging.info("--- Benchmark Evaluation Complete. Computing Metrics... ---")
    metrics = evaluator.evaluate_sessions(sessions_data)
    
    # Save output artifacts
    benchmark_results = {
        "strategy": strategy,
        "use_mock_model": use_mock,
        "metrics": metrics,
        "sessions": sessions_data
    }
    
    with open(config.benchmark_output_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_results, f, indent=2)
        
    with open(config.metrics_output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
        
    logging.info(f"Saved complete session results to: {config.benchmark_output_path}")
    logging.info(f"Saved aggregated metrics to: {config.metrics_output_path}")
    
    # Print high-level report
    print("\n" + "="*50)
    print(f" CRESCENDO DEFENSE BENCHMARK REPORT ({strategy.upper()})")
    print("="*50)
    print(f"Model ID Evaluated:            {config.model_id}")
    print(f"Mock Inference Mode:           {use_mock}")
    print(f"Total Turn Sessions:           {metrics['total_sessions']}")
    print(f"  Attack Sessions:             {metrics['attack_sessions_count']}")
    print(f"  Benign Control Sessions:     {metrics['benign_sessions_count']}")
    print(f"Total Conversation Turns:      {metrics['total_turns_processed']}")
    print("-"*50)
    print(f"Jailbreak Success Rate (JSR):  {metrics['jailbreak_success_rate'] * 100:.1f}%")
    print(f"False Positive Rate (FPR):     {metrics['false_positive_rate'] * 100:.1f}%")
    print(f"Defense Intervention Rate:     {metrics['defense_intervention_rate'] * 100:.1f}%")
    print(f"Avg Turn Latency:              {metrics['avg_latency_seconds'] * 1000:.1f} ms")
    print(f"Avg Threat Score observed:     {metrics['avg_threat_score']:.4f}")
    if metrics['avg_first_intervention_turn'] > 0:
        print(f"Avg Turn of First Intervention: {metrics['avg_first_intervention_turn']:.1f}")
    print("="*50 + "\n")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="crescendo-defense Security Benchmarking Script")
    parser.add_argument(
        "--strategy", 
        type=str, 
        choices=["strategy_a", "strategy_b"], 
        default="strategy_a",
        help="Defense Strategy configuration to load (strategy_a or strategy_b)"
    )
    parser.add_argument(
        "--live", 
        action="store_true", 
        help="Use active Hugging Face inference pipeline instead of Mock framework"
    )
    
    args = parser.parse_args()
    
    run_crescendo_benchmark(strategy=args.strategy, use_mock=not args.live)
