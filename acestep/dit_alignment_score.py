"""
DiT Alignment Score Module

This module provides lyrics-to-audio alignment using cross-attention matrices
from DiT model for generating LRC timestamps.

Refactored from lyrics_alignment_infos.py for integration with ACE-Step.
"""
import numba
import torch
import numpy as np
import torch.nn.functional as F
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple, Union


# ================= Data Classes =================
@dataclass
class TokenTimestamp:
    """Stores per-token timing information."""
    token_id: int
    text: str
    start: float
    end: float
    probability: float


@dataclass
class SentenceTimestamp:
    """Stores per-sentence timing information with token list."""
    text: str
    start: float
    end: float
    tokens: List[TokenTimestamp]
    confidence: float


# ================= DTW Algorithm (Numba Optimized) =================
@numba.jit(nopython=True)
def dtw_cpu(x: np.ndarray):
    """
    Dynamic Time Warping algorithm optimized with Numba.
    
    Args:
        x: Cost matrix of shape [N, M]
        
    Returns:
        Tuple of (text_indices, time_indices) arrays
    """
    N, M = x.shape
    # Use float32 for memory efficiency
    cost = np.ones((N + 1, M + 1), dtype=np.float32) * np.inf
    trace = -np.ones((N + 1, M + 1), dtype=np.float32)
    cost[0, 0] = 0

    for j in range(1, M + 1):
        for i in range(1, N + 1):
            c0 = cost[i - 1, j - 1]
            c1 = cost[i - 1, j]
            c2 = cost[i, j - 1]

            if c0 < c1 and c0 < c2:
                c, t = c0, 0
            elif c1 < c0 and c1 < c2:
                c, t = c1, 1
            else:
                c, t = c2, 2

            cost[i, j] = x[i - 1, j - 1] + c
            trace[i, j] = t

    return _backtrace(trace, N, M)


@numba.jit(nopython=True)
def _backtrace(trace: np.ndarray, N: int, M: int):
    """
    Optimized backtrace function for DTW.
    
    Args:
        trace: Trace matrix of shape (N+1, M+1)
        N, M: Original matrix dimensions
        
    Returns:
        Path array of shape (2, path_len) - first row is text indices, second is time indices
    """
    # Boundary handling
    trace[0, :] = 2
    trace[:, 0] = 1
    
    # Pre-allocate array, max path length is N+M
    max_path_len = N + M
    path = np.zeros((2, max_path_len), dtype=np.int32)
    
    i, j = N, M
    path_idx = max_path_len - 1
    
    while i > 0 or j > 0:
        path[0, path_idx] = i - 1  # text index
        path[1, path_idx] = j - 1  # time index
        path_idx -= 1
        
        t = trace[i, j]
        if t == 0:
            i -= 1
            j -= 1
        elif t == 1:
            i -= 1
        elif t == 2:
            j -= 1
        else:
            break
    
    actual_len = max_path_len - path_idx - 1
    return path[:, path_idx + 1:max_path_len]


# ================= Utility Functions =================
def median_filter(x: torch.Tensor, filter_width: int) -> torch.Tensor:
    """
    Apply median filter to tensor.
    
    Args:
        x: Input tensor
        filter_width: Width of median filter
        
    Returns:
        Filtered tensor
    """
    pad_width = filter_width // 2
    if x.shape[-1] <= pad_width:
        return x
    if x.ndim == 2:
        x = x[None, :]
    x = F.pad(x, (filter_width // 2, filter_width // 2, 0, 0), mode="reflect")
    result = x.unfold(-1, filter_width, 1).sort()[0][..., filter_width // 2]
    if result.ndim > 2:
        result = result.squeeze(0)
    return result


# ================= Main Aligner Class =================
class MusicStampsAligner:
    """
    Aligner class for generating lyrics timestamps from cross-attention matrices.
    
    Uses bidirectional consensus denoising and DTW for alignment.
    """
    
    def __init__(self, tokenizer):
        """
        Initialize the aligner.
        
        Args:
            tokenizer: Text tokenizer for decoding tokens
        """
        self.tokenizer = tokenizer

    def _apply_bidirectional_consensus(
        self, 
        weights_stack: torch.Tensor, 
        violence_level: float, 
        medfilt_width: int
    ) -> tuple:
        """
        Core denoising logic using bidirectional consensus.
        
        Args:
            weights_stack: Attention weights [Heads, Tokens, Frames]
            violence_level: Denoising strength coefficient
            medfilt_width: Median filter width
            
        Returns:
            Tuple of (calc_matrix, energy_matrix) as numpy arrays
        """
        # A. Bidirectional Consensus
        row_prob = F.softmax(weights_stack, dim=-1)  # Token -> Frame
        col_prob = F.softmax(weights_stack, dim=-2)  # Frame -> Token
        processed = row_prob * col_prob

        # 1. Row suppression (kill horizontal crossing lines)
        row_medians = torch.quantile(processed, 0.5, dim=-1, keepdim=True)
        processed = processed - (violence_level * row_medians)
        processed = torch.relu(processed)

        # 2. Column suppression (kill vertical crossing lines)
        col_medians = torch.quantile(processed, 0.5, dim=-2, keepdim=True)
        processed = processed - (violence_level * col_medians)
        processed = torch.relu(processed)

        # C. Power sharpening
        processed = processed ** 2

        # Energy matrix for confidence
        energy_matrix = processed.mean(dim=0).cpu().numpy()
        
        # D. Z-Score normalization
        std, mean = torch.std_mean(processed, unbiased=False)
        weights_processed = (processed - mean) / (std + 1e-9)

        # E. Median filtering
        weights_processed = median_filter(weights_processed, filter_width=medfilt_width)
        calc_matrix = weights_processed.mean(dim=0).numpy()
        
        return calc_matrix, energy_matrix

    def _preprocess_attention(
        self, 
        attention_matrix: torch.Tensor, 
        custom_config: Dict[int, List[int]], 
        violence_level: float, 
        medfilt_width: int = 7
    ) -> tuple:
        """
        Preprocess attention matrix for alignment.
        
        Args:
            attention_matrix: Attention tensor [Layers, Heads, Tokens, Frames]
            custom_config: Dict mapping layer indices to head indices
            violence_level: Denoising strength
            medfilt_width: Median filter width
            
        Returns:
            Tuple of (calc_matrix, energy_matrix, visual_matrix)
        """
        if not isinstance(attention_matrix, torch.Tensor):
            weights = torch.tensor(attention_matrix)
        else:
            weights = attention_matrix.clone()

        weights = weights.cpu().float()

        selected_tensors = []
        for layer_idx, head_indices in custom_config.items():
            for head_idx in head_indices:
                if layer_idx < weights.shape[0] and head_idx < weights.shape[1]:
                    head_matrix = weights[layer_idx, head_idx]
                    selected_tensors.append(head_matrix)

        if not selected_tensors:
            return None, None, None

        # Stack selected heads: [Heads, Tokens, Frames]
        weights_stack = torch.stack(selected_tensors, dim=0)
        visual_matrix = weights_stack.mean(dim=0).numpy()

        calc_matrix, energy_matrix = self._apply_bidirectional_consensus(
            weights_stack, violence_level, medfilt_width
        )

        return calc_matrix, energy_matrix, visual_matrix

    def stamps_align_info(
        self,
        attention_matrix: torch.Tensor,
        lyrics_tokens: List[int],
        total_duration_seconds: float,
        custom_config: Dict[int, List[int]],
        return_matrices: bool = False,
        violence_level: float = 2.0,
        medfilt_width: int = 1
    ) -> Dict[str, Any]:
        """
        Get alignment information from attention matrix.
        
        Args:
            attention_matrix: Cross-attention tensor [Layers, Heads, Tokens, Frames]
            lyrics_tokens: List of lyrics token IDs
            total_duration_seconds: Total audio duration in seconds
            custom_config: Dict mapping layer indices to head indices
            return_matrices: Whether to return intermediate matrices
            violence_level: Denoising strength
            medfilt_width: Median filter width
            
        Returns:
            Dict containing calc_matrix, lyrics_tokens, total_duration_seconds,
            and optionally energy_matrix and vis_matrix
        """
        calc_matrix, energy_matrix, visual_matrix = self._preprocess_attention(
            attention_matrix, custom_config, violence_level, medfilt_width
        )
        
        if calc_matrix is None:
            return {
                "calc_matrix": None,
                "lyrics_tokens": lyrics_tokens,
                "total_duration_seconds": total_duration_seconds,
                "error": "No valid attention heads found"
            }
        
        return_dict = {
            "calc_matrix": calc_matrix,
            "lyrics_tokens": lyrics_tokens,
            "total_duration_seconds": total_duration_seconds
        }
        
        if return_matrices:
            return_dict['energy_matrix'] = energy_matrix
            return_dict['vis_matrix'] = visual_matrix

        return return_dict

    def _decode_tokens_incrementally(self, token_ids: List[int]) -> List[str]:
        """
        Decode tokens incrementally to properly handle multi-byte UTF-8 characters.
        
        For Chinese and other multi-byte characters, the tokenizer may split them
        into multiple byte-level tokens. Decoding each token individually produces
        invalid UTF-8 sequences (showing as �). This method uses byte-level comparison
        to correctly track which characters each token contributes.
        
        Args:
            token_ids: List of token IDs
            
        Returns:
            List of decoded text for each token position
        """
        decoded_tokens = []
        prev_bytes = b""
        
        for i in range(len(token_ids)):
            # Decode tokens from start to current position
            current_text = self.tokenizer.decode(token_ids[:i+1], skip_special_tokens=False)
            current_bytes = current_text.encode('utf-8', errors='surrogatepass')
            
            # The contribution of current token is the new bytes added
            if len(current_bytes) >= len(prev_bytes):
                new_bytes = current_bytes[len(prev_bytes):]
                # Try to decode the new bytes; if incomplete, use empty string
                try:
                    token_text = new_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    # Incomplete UTF-8 sequence, this token doesn't complete a character
                    token_text = ""
            else:
                # Edge case: current decode is shorter (shouldn't happen normally)
                token_text = ""
            
            decoded_tokens.append(token_text)
            prev_bytes = current_bytes
        
        return decoded_tokens

    def token_timestamps(
        self,
        calc_matrix: np.ndarray,
        lyrics_tokens: List[int],
        total_duration_seconds: float
    ) -> List[TokenTimestamp]:
        """
        Generate per-token timestamps using DTW.
        
        Args:
            calc_matrix: Processed attention matrix [Tokens, Frames]
            lyrics_tokens: List of token IDs
            total_duration_seconds: Total audio duration
            
        Returns:
            List of TokenTimestamp objects
        """
        n_frames = calc_matrix.shape[-1]
        text_indices, time_indices = dtw_cpu(-calc_matrix.astype(np.float64))

        seconds_per_frame = total_duration_seconds / n_frames
        alignment_results = []
        
        # Use incremental decoding to properly handle multi-byte UTF-8 characters
        decoded_tokens = self._decode_tokens_incrementally(lyrics_tokens)

        for i in range(len(lyrics_tokens)):
            mask = (text_indices == i)

            if not np.any(mask):
                start = alignment_results[-1].end if alignment_results else 0.0
                end = start
                token_conf = 0.0
            else:
                times = time_indices[mask] * seconds_per_frame
                start = times[0]
                end = times[-1]
                token_conf = 0.0

            if end < start:
                end = start

            alignment_results.append(TokenTimestamp(
                token_id=lyrics_tokens[i],
                text=decoded_tokens[i],
                start=float(start),
                end=float(end),
                probability=token_conf
            ))

        return alignment_results

    def _decode_sentence_from_tokens(self, tokens: List[TokenTimestamp]) -> str:
        """
        Decode a sentence by decoding all token IDs together.
        This avoids UTF-8 encoding issues from joining individual token texts.
        
        Args:
            tokens: List of TokenTimestamp objects
            
        Returns:
            Properly decoded sentence text
        """
        token_ids = [t.token_id for t in tokens]
        return self.tokenizer.decode(token_ids, skip_special_tokens=False)

    def sentence_timestamps(
        self, 
        token_alignment: List[TokenTimestamp]
    ) -> List[SentenceTimestamp]:
        """
        Group token timestamps into sentence timestamps.
        
        Args:
            token_alignment: List of TokenTimestamp objects
            
        Returns:
            List of SentenceTimestamp objects
        """
        results = []
        current_tokens = []

        for token in token_alignment:
            current_tokens.append(token)

            if '\n' in token.text:
                # Decode all token IDs together to avoid UTF-8 issues
                full_text = self._decode_sentence_from_tokens(current_tokens)

                if full_text.strip():
                    valid_scores = [t.probability for t in current_tokens if t.probability > 0]
                    sent_conf = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

                    results.append(SentenceTimestamp(
                        text=full_text.strip(),
                        start=round(current_tokens[0].start, 3),
                        end=round(current_tokens[-1].end, 3),
                        tokens=list(current_tokens),
                        confidence=sent_conf
                    ))

                current_tokens = []

        # Handle last sentence
        if current_tokens:
            # Decode all token IDs together to avoid UTF-8 issues
            full_text = self._decode_sentence_from_tokens(current_tokens)
            if full_text.strip():
                valid_scores = [t.probability for t in current_tokens if t.probability > 0]
                sent_conf = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

                results.append(SentenceTimestamp(
                    text=full_text.strip(),
                    start=round(current_tokens[0].start, 3),
                    end=round(current_tokens[-1].end, 3),
                    tokens=list(current_tokens),
                    confidence=sent_conf
                ))

        # Normalize confidence scores
        if results:
            all_scores = [s.confidence for s in results]
            min_score = min(all_scores)
            max_score = max(all_scores)
            score_range = max_score - min_score

            if score_range > 1e-9:
                for s in results:
                    normalized_score = (s.confidence - min_score) / score_range
                    s.confidence = round(normalized_score, 2)
            else:
                for s in results:
                    s.confidence = round(s.confidence, 2)

        return results

    def format_lrc(
        self, 
        sentence_timestamps: List[SentenceTimestamp],
        include_end_time: bool = False
    ) -> str:
        """
        Format sentence timestamps as LRC lyrics format.
        
        Args:
            sentence_timestamps: List of SentenceTimestamp objects
            include_end_time: Whether to include end time (enhanced LRC format)
            
        Returns:
            LRC formatted string
        """
        lines = []
        
        for sentence in sentence_timestamps:
            # Convert seconds to mm:ss.xx format
            start_minutes = int(sentence.start // 60)
            start_seconds = sentence.start % 60
            
            if include_end_time:
                end_minutes = int(sentence.end // 60)
                end_seconds = sentence.end % 60
                timestamp = f"[{start_minutes:02d}:{start_seconds:05.2f}][{end_minutes:02d}:{end_seconds:05.2f}]"
            else:
                timestamp = f"[{start_minutes:02d}:{start_seconds:05.2f}]"
            
            # Clean the text (remove structural tags like [verse], [chorus])
            text = sentence.text
            
            lines.append(f"{timestamp}{text}")
        
        return "\n".join(lines)

    def get_timestamps_and_lrc(
        self,
        calc_matrix: np.ndarray,
        lyrics_tokens: List[int],
        total_duration_seconds: float
    ) -> Dict[str, Any]:
        """
        Convenience method to get both timestamps and LRC in one call.
        
        Args:
            calc_matrix: Processed attention matrix
            lyrics_tokens: List of token IDs
            total_duration_seconds: Total audio duration
            
        Returns:
            Dict containing token_timestamps, sentence_timestamps, and lrc_text
        """
        token_stamps = self.token_timestamps(
            calc_matrix=calc_matrix,
            lyrics_tokens=lyrics_tokens,
            total_duration_seconds=total_duration_seconds
        )
        
        sentence_stamps = self.sentence_timestamps(token_stamps)
        lrc_text = self.format_lrc(sentence_stamps)
        
        return {
            "token_timestamps": token_stamps,
            "sentence_timestamps": sentence_stamps,
            "lrc_text": lrc_text
        }


class MusicLyricScorer:
    """
    Scorer class for evaluating lyrics-to-audio alignment quality.

    Focuses on calculating alignment quality metrics (Coverage, Monotonicity, Confidence)
    using tensor operations for potential differentiability or GPU acceleration.
    """

    def __init__(self, tokenizer: Any):
        """
        Initialize the aligner.

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
        # Ratio of lyric lines that have significant energy peak
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
        # Check if the "center of mass" of lyric lines moves forward in time
        col_indices = torch.arange(cols, device=device, dtype=torch.float64)

        # Zero out low energy noise
        weights = torch.where(
            energy_matrix > time_weight,
            energy_matrix,
            torch.zeros_like(energy_matrix)
        )

        sum_w = weights.sum(dim=1)
        sum_t = (weights * col_indices).sum(dim=1)

        # Calculate centroids
        centroids = torch.full((rows,), -1.0, device=device, dtype=torch.float64)
        valid_w_mask = sum_w > 1e-9
        centroids[valid_w_mask] = sum_t[valid_w_mask] / sum_w[valid_w_mask]

        # Extract sequence of valid lyrics centroids
        valid_sequence_mask = is_lyrics_row & (centroids >= 0)
        sung_centroids = centroids[valid_sequence_mask]

        cnt = sung_centroids.shape[0]
        if cnt > 1:
            curr_c = sung_centroids[:-1]
            next_c = sung_centroids[1:]

            # Check non-decreasing order with overlap tolerance
            non_decreasing = (next_c >= (curr_c - overlap_frames)).double().sum()
            pairs = torch.tensor(cnt - 1, device=device, dtype=torch.float64)
            monotonicity_score = non_decreasing / pairs
        else:
            monotonicity_score = torch.tensor(1.0, device=device, dtype=torch.float64)

        # ================= C. Path Confidence =================
        # Average energy along the optimal path
        if path_coords.shape[0] > 0:
            p_rows = path_coords[:, 0]
            p_cols = path_coords[:, 1]

            path_energies = energy_matrix[p_rows, p_cols]
            step_weights = torch.ones_like(path_energies)

            # Lower weight for instrumental/tag steps
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
            Dict or AlignmentInfo object containing path and masks.
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
        # Uses self.tokenizer internally
        type_mask = self._generate_token_type_mask(token_ids)

        # Safety check for shape mismatch
        if len(type_mask) != energy_matrix.shape[0]:
            # Fallback to all lyrics if shapes don't align
            type_mask = np.ones(energy_matrix.shape[0], dtype=np.int32)

        # 2. DTW Pathfinding
        # Using negative calc_matrix because DTW minimizes cost
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
            AlignmentScore object containing individual metrics and final score.
        """
        # Ensure Inputs are Tensors on the correct device
        if isinstance(energy_matrix, torch.Tensor):
            device = energy_matrix.device
        elif isinstance(type_mask, torch.Tensor):
            device = type_mask.device
        elif isinstance(path_coords, torch.Tensor):
            device = path_coords.device
        else:
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")
            elif torch.cuda.is_available():
                device = torch.device("cuda")
            else:
                device = torch.device("cpu")
            energy_matrix = torch.tensor(energy_matrix, device=device, dtype=torch.float32)

        if not isinstance(energy_matrix, torch.Tensor):
            energy_matrix = torch.tensor(energy_matrix, device=device, dtype=torch.float32)

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