"""
DiT Alignment Module

Provides lyrics-to-audio timestamp alignment using cross-attention matrices
from the DiT model.  Produces LRC-format timestamps via bidirectional
consensus denoising and DTW.
"""
import numpy as np
import torch
import torch.nn.functional as F
from dataclasses import dataclass
from typing import List, Dict, Any

from acestep.core.scoring._dtw import dtw_cpu, median_filter


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
        invalid UTF-8 sequences (showing as \ufffd). This method uses byte-level comparison
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
