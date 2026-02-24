"""
DiT Lyrics Quality Scorer

Evaluates lyrics-to-audio alignment quality using cross-attention energy
matrices.  Computes Coverage, Monotonicity, and Path Confidence metrics
via tensor operations.
"""
import numpy as np
import torch
from typing import Any, Dict, List, Optional, Tuple, Union

from acestep.core.scoring._dtw import dtw_cpu, median_filter


class MusicLyricScorer:
    """
    Scorer class for evaluating lyrics-to-audio alignment quality.

    Focuses on calculating alignment quality metrics (Coverage, Monotonicity, Confidence)
    using tensor operations for potential differentiability or GPU acceleration.
    """

    def __init__(self, tokenizer: Any):
        """
        Initialize the scorer.

        Args:
            tokenizer: Tokenizer instance (must implement .decode()).
        """
        self.tokenizer = tokenizer

    def _generate_token_type_mask(self, token_ids: List[int]) -> np.ndarray:
        """
        Generate a mask distinguishing lyrics (1) from structural tags (0).
        Uses self.tokenizer to decode tokens.

        Args:
            token_ids: List of token IDs.

        Returns:
            Numpy array of shape [len(token_ids)] with 1 or 0.
        """
        decoded_tokens = [self.tokenizer.decode([tid]) for tid in token_ids]
        mask = np.ones(len(token_ids), dtype=np.int32)
        in_bracket = False

        for i, token_str in enumerate(decoded_tokens):
            if '[' in token_str:
                in_bracket = True
            if in_bracket:
                mask[i] = 0
            if ']' in token_str:
                in_bracket = False
                mask[i] = 0
        return mask

    def _preprocess_attention(
            self,
            attention_matrix: Union[torch.Tensor, np.ndarray],
            custom_config: Dict[int, List[int]],
            medfilt_width: int = 1
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[torch.Tensor]]:
        """
        Extracts and normalizes the attention matrix.

        Logic V4: Uses Min-Max normalization to highlight energy differences.

        Args:
            attention_matrix: Raw attention tensor [Layers, Heads, Tokens, Frames].
            custom_config: Config mapping layers to heads.
            medfilt_width: Width for median filtering.

        Returns:
            Tuple of (calc_matrix, energy_matrix, avg_weights_tensor).
        """
        # 1. Prepare Tensor
        if not isinstance(attention_matrix, torch.Tensor):
            weights = torch.tensor(attention_matrix)
        else:
            weights = attention_matrix.clone()
        weights = weights.cpu().float()

        # 2. Select Heads based on config
        selected_tensors = []
        for layer_idx, head_indices in custom_config.items():
            for head_idx in head_indices:
                if layer_idx < weights.shape[0] and head_idx < weights.shape[1]:
                    selected_tensors.append(weights[layer_idx, head_idx])

        if not selected_tensors:
            return None, None, None

        weights_stack = torch.stack(selected_tensors, dim=0)

        # 3. Average Heads
        avg_weights = weights_stack.mean(dim=0)  # [Tokens, Frames]

        # 4. Preprocessing Logic
        # Min-Max normalization preserving energy distribution
        # Median filter is applied to the energy matrix
        energy_tensor = median_filter(avg_weights, filter_width=medfilt_width)
        energy_matrix = energy_tensor.numpy()

        e_min, e_max = energy_matrix.min(), energy_matrix.max()

        if e_max - e_min > 1e-9:
            energy_matrix = (energy_matrix - e_min) / (e_max - e_min)
        else:
            energy_matrix = np.zeros_like(energy_matrix)

        # Contrast enhancement for DTW pathfinding
        # calc_matrix is used for pathfinding, energy_matrix for scoring
        calc_matrix = energy_matrix ** 2

        return calc_matrix, energy_matrix, avg_weights

    def _compute_alignment_metrics(
            self,
            energy_matrix: torch.Tensor,
            path_coords: torch.Tensor,
            type_mask: torch.Tensor,
            time_weight: float = 0.01,
            overlap_frames: float = 9.0,
            instrumental_weight: float = 1.0
    ) -> Tuple[float, float, float]:
        """
        Core metric calculation logic using high-precision Tensor operations.

        Args:
            energy_matrix: Normalized energy [Rows, Cols].
            path_coords: DTW path coordinates [Steps, 2].
            type_mask: Token type mask [Rows] (1=Lyrics, 0=Tags).
            time_weight: Minimum energy threshold for monotonicity.
            overlap_frames: Allowed overlap for monotonicity check.
            instrumental_weight: Weight for non-lyric tokens in confidence calc.

        Returns:
            Tuple of (coverage, monotonicity, confidence).
        """
        # Ensure high precision for internal calculation
        energy_matrix = energy_matrix.to(dtype=torch.float64)
        path_coords = path_coords.long()
        type_mask = type_mask.long()

        device = energy_matrix.device
        rows, cols = energy_matrix.shape

        is_lyrics_row = (type_mask == 1)

        # ================= A. Coverage Score =================
        row_max_energies = energy_matrix.max(dim=1).values
        total_sung_rows = is_lyrics_row.sum().double()

        coverage_threshold = 0.1
        valid_sung_mask = is_lyrics_row & (row_max_energies > coverage_threshold)
        valid_sung_rows = valid_sung_mask.sum().double()

        if total_sung_rows > 0:
            coverage_score = valid_sung_rows / total_sung_rows
        else:
            coverage_score = torch.tensor(1.0, device=device, dtype=torch.float64)

        # ================= B. Monotonicity Score =================
        col_indices = torch.arange(cols, device=device, dtype=torch.float64)

        weights = torch.where(
            energy_matrix > time_weight,
            energy_matrix,
            torch.zeros_like(energy_matrix)
        )

        sum_w = weights.sum(dim=1)
        sum_t = (weights * col_indices).sum(dim=1)

        centroids = torch.full((rows,), -1.0, device=device, dtype=torch.float64)
        valid_w_mask = sum_w > 1e-9
        centroids[valid_w_mask] = sum_t[valid_w_mask] / sum_w[valid_w_mask]

        valid_sequence_mask = is_lyrics_row & (centroids >= 0)
        sung_centroids = centroids[valid_sequence_mask]

        cnt = sung_centroids.shape[0]
        if cnt > 1:
            curr_c = sung_centroids[:-1]
            next_c = sung_centroids[1:]

            non_decreasing = (next_c >= (curr_c - overlap_frames)).double().sum()
            pairs = torch.tensor(cnt - 1, device=device, dtype=torch.float64)
            monotonicity_score = non_decreasing / pairs
        else:
            monotonicity_score = torch.tensor(1.0, device=device, dtype=torch.float64)

        # ================= C. Path Confidence =================
        if path_coords.shape[0] > 0:
            p_rows = path_coords[:, 0]
            p_cols = path_coords[:, 1]

            path_energies = energy_matrix[p_rows, p_cols]
            step_weights = torch.ones_like(path_energies)

            is_inst_step = (type_mask[p_rows] == 0)
            step_weights[is_inst_step] = instrumental_weight

            total_energy = (path_energies * step_weights).sum()
            total_steps = step_weights.sum()

            if total_steps > 0:
                path_confidence = total_energy / total_steps
            else:
                path_confidence = torch.tensor(0.0, device=device, dtype=torch.float64)
        else:
            path_confidence = torch.tensor(0.0, device=device, dtype=torch.float64)

        return coverage_score.item(), monotonicity_score.item(), path_confidence.item()

    def lyrics_alignment_info(
            self,
            attention_matrix: Union[torch.Tensor, np.ndarray],
            token_ids: List[int],
            custom_config: Dict[int, List[int]],
            return_matrices: bool = False,
            medfilt_width: int = 1
    ) -> Dict[str, Any]:
        """
        Generates alignment path and processed matrices.

        Args:
            attention_matrix: Input attention tensor.
            token_ids: Corresponding token IDs.
            custom_config: Layer/Head configuration.
            return_matrices: If True, returns matrices in the output.
            medfilt_width: Median filter width.

        Returns:
            Dict containing path, masks, and energy matrix.
        """
        calc_matrix, energy_matrix, vis_matrix = self._preprocess_attention(
            attention_matrix, custom_config, medfilt_width
        )

        if calc_matrix is None:
            return {
                "calc_matrix": None,
                "error": "No valid attention heads found"
            }

        # 1. Generate Semantic Mask (1=Lyrics, 0=Tags)
        type_mask = self._generate_token_type_mask(token_ids)

        # Safety check for shape mismatch
        if len(type_mask) != energy_matrix.shape[0]:
            type_mask = np.ones(energy_matrix.shape[0], dtype=np.int32)

        # 2. DTW Pathfinding
        text_indices, time_indices = dtw_cpu(-calc_matrix.astype(np.float32))
        path_coords = np.stack([text_indices, time_indices], axis=1)

        return_dict = {
            "path_coords": path_coords,
            "type_mask": type_mask,
            "energy_matrix": energy_matrix
        }
        if return_matrices:
            return_dict['calc_matrix'] = calc_matrix
            return_dict['vis_matrix'] = vis_matrix

        return return_dict

    def calculate_score(
            self,
            energy_matrix: Union[torch.Tensor, np.ndarray],
            type_mask: Union[torch.Tensor, np.ndarray],
            path_coords: Union[torch.Tensor, np.ndarray],
            time_weight: float = 0.01,
            overlap_frames: float = 9.0,
            instrumental_weight: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates the final alignment score based on pre-computed components.

        Args:
            energy_matrix: Processed energy matrix.
            type_mask: Token type mask.
            path_coords: DTW path coordinates.
            time_weight: Minimum energy threshold for monotonicity.
            overlap_frames: Allowed backward movement frames.
            instrumental_weight: Weight for non-lyric path steps.

        Returns:
            Dict containing ``lyrics_score`` key with the final score.
        """
        # Always compute on CPU — the scoring matrices are small and this
        # avoids occupying GPU VRAM that DiT / VAE / LM need.
        _score_device = "cpu"
        if not isinstance(energy_matrix, torch.Tensor):
            energy_matrix = torch.tensor(energy_matrix, device=_score_device, dtype=torch.float32)
        else:
            energy_matrix = energy_matrix.to(device=_score_device, dtype=torch.float32)

        device = energy_matrix.device

        if not isinstance(type_mask, torch.Tensor):
            type_mask = torch.tensor(type_mask, device=device, dtype=torch.long)
        else:
            type_mask = type_mask.to(device=device, dtype=torch.long)

        if not isinstance(path_coords, torch.Tensor):
            path_coords = torch.tensor(path_coords, device=device, dtype=torch.long)
        else:
            path_coords = path_coords.to(device=device, dtype=torch.long)

        # Compute Metrics
        coverage, monotonicity, confidence = self._compute_alignment_metrics(
            energy_matrix=energy_matrix,
            path_coords=path_coords,
            type_mask=type_mask,
            time_weight=time_weight,
            overlap_frames=overlap_frames,
            instrumental_weight=instrumental_weight
        )

        # Final Score Calculation
        # (Cov^2 * Mono^2 * Conf)
        final_score = (coverage ** 2) * (monotonicity ** 2) * confidence
        final_score = float(np.clip(final_score, 0.0, 1.0))

        return {
            "lyrics_score": round(final_score, 4)
        }
