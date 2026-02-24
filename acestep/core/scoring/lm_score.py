"""
LM Perplexity / PMI Scoring Module

Implements perplexity-based scoring for generated audio codes using a
language model.  Provides PMI, top-k recall, metadata recall, and a
composite reward score.
"""
import contextlib
import math
import re

import torch
import torch.nn.functional as F
import yaml
from loguru import logger
from typing import Tuple, Optional, Dict, Any, List


def pmi_score(log_prob_conditional: float, log_prob_unconditional: float) -> float:
    """
    Calculate Pointwise Mutual Information (PMI) score.

    PMI = log P(condition|codes) - log P(condition)
        = log [P(codes|condition) / P(codes)]

    This removes the bias from P(condition) and measures how much the codes
    improve our ability to predict the condition.

    Args:
        log_prob_conditional: Average log probability of condition given codes
        log_prob_unconditional: Average log probability of condition without codes

    Returns:
        PMI score (higher is better, can be positive or negative)
        - Positive: codes improve prediction -> good match
        - Zero: codes don't help -> no correlation
        - Negative: codes hurt prediction -> poor match
    """
    return log_prob_conditional - log_prob_unconditional


def pmi_to_normalized_score(pmi: float, scale: float = 0.1) -> float:
    """
    Convert PMI score to normalized [0, 1] range using sigmoid function.

    score = sigmoid(PMI / scale) = 1 / (1 + exp(-PMI / scale))

    Args:
        pmi: PMI score (can be positive or negative)
        scale: Scale parameter to control sensitivity (default 0.1)
               - Smaller scale: more sensitive to PMI changes
               - Larger scale: less sensitive to PMI changes

    Returns:
        Normalized score in [0, 1] range, where:
        - PMI > 0 -> score > 0.5 (good match)
        - PMI = 0 -> score = 0.5 (neutral)
        - PMI < 0 -> score < 0.5 (poor match)

    Examples (scale=1.0):
        PMI=2.0  -> score~0.88  (excellent)
        PMI=1.0  -> score~0.73  (good)
        PMI=0.0  -> score=0.50  (neutral)
        PMI=-1.0 -> score~0.27  (poor)
        PMI=-2.0 -> score~0.12  (bad)
    """
    return 1.0 / (1.0 + math.exp(-pmi / scale))


@contextlib.contextmanager
def _load_scoring_model_context(llm_handler):
    """
    Context manager that loads the HF scoring model to the accelerator device
    before use and offloads it back to CPU afterwards.

    For the ``pt`` backend the existing ``_load_model_context()`` already
    handles offloading, so we just delegate to it.  For ``vllm`` / ``mlx``
    backends, ``get_hf_model_for_scoring()`` caches a *separate* HF model
    that would otherwise stay on GPU permanently -- here we move it to GPU
    only for the duration of the scoring forward pass and move it back to
    CPU when done, freeing VRAM for DiT / VAE.
    """
    backend = getattr(llm_handler, "llm_backend", "pt")

    if backend == "pt":
        # pt backend: _load_model_context already handles GPU <-> CPU
        with llm_handler._load_model_context():
            yield
        return

    # vllm / mlx: manage the cached HF model ourselves
    model = llm_handler.get_hf_model_for_scoring()
    if model is None:
        yield
        return

    offload = getattr(llm_handler, "offload_to_cpu", False)
    device = llm_handler.device if hasattr(llm_handler, "device") else "cpu"

    if offload and hasattr(model, "to"):
        logger.info(f"[scoring] Loading HF scoring model to {device}")
        model.to(device)

    try:
        yield
    finally:
        if offload and hasattr(model, "to"):
            logger.info("[scoring] Offloading HF scoring model to CPU")
            model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available() and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()


def _get_logits_and_target_for_scoring(llm_handler, formatted_prompt: str,
                                       target_text: str) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Args:
        llm_handler: The handler containing the model and tokenizer.
        formatted_prompt: The input context.
        target_text: The text we want to calculate probability/recall for.

    Returns:
        Tuple of (target_logits, target_ids)
        - target_logits: Logits used to predict the target tokens.
        - target_ids: The ground truth token IDs of the target.
    """
    model = llm_handler.get_hf_model_for_scoring()
    tokenizer = llm_handler.llm_tokenizer

    # Determine the device the model is *currently* on (it may be on CPU
    # if offload_to_cpu is active -- _load_scoring_model_context will move
    # it to the accelerator before the forward pass).
    backend = getattr(llm_handler, "llm_backend", "pt")
    if backend == "pt":
        device = llm_handler.device
    else:
        # For vllm/mlx the scoring model may be on CPU right now;
        # use the handler's target device so tensors land on the right device
        # once the model is moved there by the context manager.
        device = llm_handler.device if hasattr(llm_handler, "device") else next(model.parameters()).device

    # 1. Tokenize prompt ONLY to get its length (used for slicing later).
    #    We must ensure special tokens are added to count the offset correctly.
    prompt_tokens_temp = tokenizer(formatted_prompt, return_tensors="pt", add_special_tokens=True)
    prompt_len = prompt_tokens_temp['input_ids'].shape[1]

    # 2. Tokenize the FULL text (Prompt + Target).
    #    This ensures subword merging at boundaries is handled correctly by the tokenizer.
    full_text = formatted_prompt + target_text
    full_tokens = tokenizer(full_text, return_tensors="pt", padding=False, truncation=True, add_special_tokens=True).to(device)

    input_ids = full_tokens['input_ids']

    # Safety check: if target was empty or truncated entirely
    if input_ids.shape[1] <= prompt_len:
        return torch.empty(0, device=device), torch.empty(0, device=device)

    # 3. Forward Pass (Teacher Forcing)
    #    _load_scoring_model_context ensures the model is on-device for the
    #    forward pass and offloaded back to CPU afterwards.
    with torch.no_grad():
        with _load_scoring_model_context(llm_handler):
            outputs = model(input_ids=input_ids, attention_mask=full_tokens['attention_mask'])
            all_logits = outputs.logits  # [1, seq_len, vocab_size]

    # 4. Extract Logits and Labels -- move to CPU so downstream scoring
    #    does not keep large vocab-sized tensors on GPU.
    target_logits = all_logits[0, prompt_len - 1:-1, :].cpu()  # [target_len, vocab_size]
    target_ids = input_ids[0, prompt_len:].cpu()  # [target_len]

    return target_logits, target_ids


# ==============================================================================
# Scoring Logic
# ==============================================================================


def _calculate_topk_recall(llm_handler,
                           formatted_prompt: str,
                           target_text: str,
                           topk: int = 10) -> Tuple[float, Dict[int, float]]:
    """
    Calculate top-k recall for target text given prompt.
    Checks if the ground truth token is within the top-k probabilities at each step.
    """
    # Use the fixed helper to get aligned logits/labels
    pred_logits, target_ids = _get_logits_and_target_for_scoring(llm_handler, formatted_prompt, target_text)

    if target_ids.shape[0] == 0:
        return 0.0, {}

    target_len = target_ids.shape[0]

    # Get top-k indices for all positions at once
    # topk_indices: [target_len, topk]
    _, topk_indices = torch.topk(pred_logits, k=min(topk, pred_logits.shape[-1]), dim=-1)

    recall_per_k = {}
    position_scores = []

    # Convert to list for faster CPU iteration
    target_ids_list = target_ids.tolist()
    topk_indices_list = topk_indices.tolist()

    for k in range(1, topk + 1):
        hits = 0
        for pos in range(target_len):
            gt_token = target_ids_list[pos]
            # Check the top-k slice
            topk_at_pos = topk_indices_list[pos][:k]

            if gt_token in topk_at_pos:
                hits += 1
                # Calculate position-weighted score only once (when k=topk)
                if k == topk:
                    rank = topk_at_pos.index(gt_token) + 1
                    # Rank 1 = 1.0, Rank k = small positive
                    position_weight = 1.0 - (rank - 1) / topk
                    position_scores.append(position_weight)

        recall_per_k[k] = hits / target_len if target_len > 0 else 0.0

    # Fill scores for positions where GT was NOT in top-k
    while len(position_scores) < target_len:
        position_scores.append(0.0)

    average_recall = sum(position_scores) / len(position_scores) if position_scores else 0.0

    return average_recall, recall_per_k


def _calculate_metadata_recall(llm_handler,
                               formatted_prompt: str,
                               fields_dict: Dict[str, Any],
                               topk: int = 10) -> Dict[str, float]:
    """
    Args:
        fields_dict: Dictionary of {field_name: field_value}
    """
    if not fields_dict:
        return {}

    field_scores = {}

    for field_name in sorted(fields_dict.keys()):
        # Construct target text for this specific field
        # e.g. <think>\nbpm: 120\n</think>\n
        field_yaml = yaml.dump({field_name: fields_dict[field_name]}, allow_unicode=True, sort_keys=True).strip()
        field_target_text = f"<think>\n{field_yaml}\n</think>\n"

        # Calculate recall using the robust logic
        avg_score, _ = _calculate_topk_recall(llm_handler, formatted_prompt, field_target_text, topk=topk)

        field_scores[field_name] = avg_score
        logger.debug(f"Recall for {field_name}: {avg_score:.4f}")

    return field_scores


def _calculate_log_prob(
        llm_handler,
        formatted_prompt: str,
        target_text: str,
        temperature: float = 1.0  # Kept for API compatibility, but ignored for scoring
) -> float:
    """
    Calculate average log probability of target text given prompt.
    """
    pred_logits, target_ids = _get_logits_and_target_for_scoring(llm_handler, formatted_prompt, target_text)

    if target_ids.shape[0] == 0:
        return float('-inf')

    # FIX: Do not divide by temperature.
    # Log-probability for PMI/Perplexity should be exact.

    # Calculate log probabilities (log_softmax)
    log_probs = F.log_softmax(pred_logits, dim=-1)  # [target_len, vocab_size]

    # Gather log probabilities of the ground truth tokens
    target_log_probs = log_probs[torch.arange(target_ids.shape[0]), target_ids]

    # Return average log probability
    mean_log_prob = target_log_probs.mean().item()

    return mean_log_prob


def calculate_reward_score(
    scores: Dict[str, float],
    weights_config: Optional[Dict[str, float]] = None
) -> Tuple[float, str]:
    """
    Reward Model Calculator: Computes a final reward based on user priorities.

    Priority Logic:
        1. Caption (Highest): The overall vibe/style must match.
        2. Lyrics (Medium): Content accuracy is important but secondary to vibe.
        3. Metadata (Lowest): Technical constraints (BPM, Key) allow for slight deviations.

    Strategy: Dynamic Weighted Sum
    - Metadata fields are aggregated into a single 'metadata' score first.
    - Weights are dynamically renormalized if any component (e.g., lyrics) is missing.

    Args:
        scores: Dictionary of raw scores (0.0 - 1.0) from the evaluation module.
        weights_config: Optional custom weights. Defaults to:
                        Caption (50%), Lyrics (30%), Metadata (20%).

    Returns:
        final_reward: The calculated reward score (0.0 - 1.0).
        explanation: A formatted string explaining how the score was derived.
    """

    # 1. Default Preference Configuration
    # These weights determine the relative importance of each component.
    if weights_config is None:
        weights_config = {
            'caption': 0.50,  # High priority: Style/Vibe
            'lyrics':  0.30,  # Medium priority: Content
            'metadata': 0.20  # Low priority: Technical details
        }

    # 2. Extract and Group Scores
    # Caption and Lyrics are standalone high-level features.
    caption_score = scores.get('caption')
    lyrics_score = scores.get('lyrics')

    # Metadata fields (bpm, key, duration, etc.) are aggregated.
    # We treat them as a single "Technical Score" to prevent them from
    # diluting the weight of Caption/Lyrics simply by having many fields.
    meta_scores_list = [
        val for key, val in scores.items()
        if key not in ['caption', 'lyrics']
    ]

    # Calculate average of all metadata fields (if any exist)
    meta_aggregate_score = None
    if meta_scores_list:
        meta_aggregate_score = sum(meta_scores_list) / len(meta_scores_list)

    # 3. specific Active Components & Dynamic Weighting
    # We only include components that actually exist in this generation.
    active_components = {}

    if caption_score is not None:
        active_components['caption'] = (caption_score, weights_config['caption'])

    if lyrics_score is not None:
        active_components['lyrics'] = (lyrics_score, weights_config['lyrics'])

    if meta_aggregate_score is not None:
        active_components['metadata'] = (meta_aggregate_score, weights_config['metadata'])

    # 4. Calculate Final Weighted Score
    total_base_weight = sum(w for _, w in active_components.values())
    total_score = 0.0

    breakdown_lines = []

    if total_base_weight == 0:
        return 0.0, "❌ No valid scores available to calculate reward."

    # Sort by weight (importance) for display
    sorted_components = sorted(active_components.items(), key=lambda x: x[1][1], reverse=True)

    for name, (score, base_weight) in sorted_components:
        # Renormalize weight: If lyrics are missing, caption/metadata weights scale up proportionately.
        normalized_weight = base_weight / total_base_weight
        weighted_contribution = score * normalized_weight
        total_score += weighted_contribution

        breakdown_lines.append(
            f"  • {name.title():<8} | Score: {score:.4f} | Weight: {normalized_weight:.2f} "
            f"-> Contrib: +{weighted_contribution:.4f}"
        )

    return total_score, "\n".join(breakdown_lines)

# ==============================================================================
# Main Public API
# ==============================================================================


def calculate_pmi_score_per_condition(
    llm_handler,
    audio_codes: str,
    caption: str = "",
    lyrics: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    temperature: float = 1.0,
    topk: int = 10,
    score_scale: float = 0.1,
) -> Tuple[Dict[str, float], float, str]:
    """
    Calculate quality score separately for each condition.
    - Metadata: Uses Top-k Recall.
    - Caption/Lyrics: Uses PMI (Normalized).
    """
    if not llm_handler.llm_initialized:
        return {}, 0.0, "❌ LLM not initialized"

    if not audio_codes or not audio_codes.strip():
        return {}, 0.0, "❌ No audio codes provided"

    if "caption" not in metadata:
        metadata['caption'] = caption

    formatted_prompt = llm_handler.build_formatted_prompt_for_understanding(audio_codes=audio_codes, is_negative_prompt=False)
    prompt_uncond = llm_handler.build_formatted_prompt_for_understanding(audio_codes="NO USER INPUT", is_negative_prompt=False)
    try:
        # 1. Calculate Recall for Metadata Fields
        if metadata and isinstance(metadata, dict):
            scores = {}
            # Define which fields use which metric
            metadata_recall_keys = ['bpm', 'duration', 'genres', 'keyscale', 'language', 'timesignature']
            metadata_pmi_keys = ['caption']
            for key in metadata_recall_keys:
                if key in metadata and metadata[key] is not None:
                    recall_metadata = {key: metadata[key]}
                    field_scores = _calculate_metadata_recall(llm_handler, formatted_prompt, recall_metadata, topk=topk)
                    scores.update(field_scores)

            # 2. Calculate PMI for Caption
            for key in metadata_pmi_keys:
                if key in metadata and metadata[key] is not None:
                    cot_yaml = yaml.dump({key: metadata[key]}, allow_unicode=True, sort_keys=True).strip()
                    target_text = f"<think>\n{cot_yaml}\n</think>\n"

                    log_prob_cond = _calculate_log_prob(llm_handler, formatted_prompt, target_text)
                    log_prob_uncond = _calculate_log_prob(llm_handler, prompt_uncond, target_text)

                    pmi_normalized = pmi_to_normalized_score(log_prob_cond - log_prob_uncond, scale=score_scale)
                    scores[key] = pmi_normalized

        # 3. Calculate PMI for Lyrics
        if lyrics:
            target_text = f"<think>\n</think>\n# Lyric\n{lyrics}\n"

            log_prob_cond = _calculate_log_prob(llm_handler, formatted_prompt, target_text)

            prompt_uncond = llm_handler.build_formatted_prompt_for_understanding(audio_codes="NO USER INPUT", is_negative_prompt=False)
            log_prob_uncond = _calculate_log_prob(llm_handler, prompt_uncond, target_text)

            scores['lyrics'] = pmi_to_normalized_score(log_prob_cond - log_prob_uncond, scale=score_scale)

        if not scores:
            return {}, 0.0, "❌ No conditions to evaluate"

        # 4. Global Score
        global_score = sum(scores.values()) / len(scores)
        global_score, breakdown_lines = calculate_reward_score(scores)

        # Status Message
        status_lines = [breakdown_lines, "\n✅ Per-condition scores (0-1):"]
        for key, score in sorted(scores.items()):
            metric = "Top-k Recall" if key in metadata_recall_keys else "PMI (Norm)"
            status_lines.append(f"  {key}: {score:.4f} ({metric})")
        status = "\n".join(status_lines)
        logger.info(f"Calculated scores: {global_score:.4f}\n{status}")
        return scores, global_score, status

    except Exception as e:
        import traceback
        error_msg = f"❌ Error: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {}, float('-inf'), error_msg
