"""
ACE-Step 1.5 Inference Test
- DiT: acestep-v15-xl-turbo (4B)
- LM: acestep-5Hz-lm-4B
- Backend: MLX (Apple Silicon)
"""
import os
import sys
import time
import shutil

# Disable tokenizers parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(PROJECT_ROOT, "checkpoints")
OUTPUT_DIR = PROJECT_ROOT
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "test_output.wav")

def main():
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    # ── Step 1: Initialize DiT Handler ──
    print("=" * 60)
    print("[Phase 4] Initializing DiT handler (acestep-v15-xl-turbo)...")
    print("=" * 60)

    dit_handler = AceStepHandler()
    t0 = time.time()
    status_msg, success = dit_handler.initialize_service(
        project_root=PROJECT_ROOT,
        config_path="acestep-v15-xl-turbo",
        device="mps",
        use_mlx_dit=True,
    )
    dit_load_time = time.time() - t0

    print(f"DiT status: {status_msg}")
    if not success:
        print("ERROR: DiT initialization failed!")
        sys.exit(1)
    print(f"DiT load time: {dit_load_time:.2f}s")

    # ── Step 2: Initialize LLM Handler ──
    print()
    print("=" * 60)
    print("[Phase 4] Initializing LLM handler (acestep-5Hz-lm-4B, MLX)...")
    print("=" * 60)

    llm_handler = LLMHandler()
    t0 = time.time()
    status_msg, success = llm_handler.initialize(
        checkpoint_dir=CHECKPOINT_DIR,
        lm_model_path="acestep-5Hz-lm-4B",
        backend="mlx",
        device="mps",
    )
    llm_load_time = time.time() - t0

    print(f"LLM status: {status_msg}")
    if not success:
        print("ERROR: LLM initialization failed!")
        sys.exit(1)
    print(f"LLM load time: {llm_load_time:.2f}s")

    # ── Step 3: Generate test audio ──
    print()
    print("=" * 60)
    print("[Phase 4] Generating test audio (15s, instrumental)...")
    print("=" * 60)

    params = GenerationParams(
        task_type="text2music",
        caption="upbeat electronic dance music with synthesizer and drum machine, energetic and bright",
        lyrics="[Instrumental]",
        instrumental=True,
        duration=15,
        bpm=128,
        keyscale="C Major",
        inference_steps=8,
        seed=42,
    )

    config = GenerationConfig(
        batch_size=1,
        use_random_seed=False,
        audio_format="wav",
    )

    t0 = time.time()
    result = generate_music(
        dit_handler, llm_handler, params, config,
        save_dir=OUTPUT_DIR,
    )
    inference_time = time.time() - t0

    if not result.success:
        print(f"ERROR: Generation failed: {result.error}")
        sys.exit(1)

    # ── Step 4: Save as test_output.wav ──
    if result.audios:
        generated_path = result.audios[0]["path"]
        if generated_path != OUTPUT_FILE:
            shutil.copy2(generated_path, OUTPUT_FILE)
        file_size_kb = os.path.getsize(OUTPUT_FILE) / 1024
        print(f"Output file: {OUTPUT_FILE}")
        print(f"File size: {file_size_kb:.1f} KB")
    else:
        print("ERROR: No audio generated!")
        sys.exit(1)

    # ── Step 5: Print timing summary ──
    time_costs = result.extra_outputs.get("time_costs", {})
    print()
    print("=" * 60)
    print("[Phase 4] Inference Test Results")
    print("=" * 60)
    print(f"  DiT load time:      {dit_load_time:.2f}s")
    print(f"  LLM load time:      {llm_load_time:.2f}s")
    print(f"  Total model load:   {dit_load_time + llm_load_time:.2f}s")
    print(f"  Inference time:     {inference_time:.2f}s")
    if time_costs:
        print(f"    LM Phase 1:       {time_costs.get('lm_phase1_time', 0):.2f}s")
        print(f"    LM Phase 2:       {time_costs.get('lm_phase2_time', 0):.2f}s")
        print(f"    DiT total:        {time_costs.get('dit_total_time_cost', 0):.2f}s")
        print(f"    Pipeline total:   {time_costs.get('pipeline_total_time', 0):.2f}s")
    print(f"  Output: {OUTPUT_FILE} ({file_size_kb:.1f} KB)")
    print(f"  Status: PASS")

if __name__ == "__main__":
    main()
