"""
Token precomputation mixin for constrained decoding.

This module provides the TokenPrecomputeMixin class, which encapsulates all
token table precomputation logic used by MetadataConstrainedLogitsProcessor.
It pre-computes commonly used token IDs (digits, notes, sharps/flats, etc.),
identifies audio code tokens in the vocabulary, and builds mask tensors for
efficient whitelisting/blacklisting during constrained generation.
"""

import re
from typing import Optional, Dict, List, Tuple, Set

import torch
from loguru import logger

from acestep.constants import (
    KEYSCALE_NOTES,
    VALID_KEYSCALES,
    VALID_LANGUAGES,
)


# Maximum valid audio code value (codebook size = 64000)
MAX_AUDIO_CODE = 63999


class TokenPrecomputeMixin:
    """Mixin for token table precomputation used by MetadataConstrainedLogitsProcessor.

    This mixin extracts the token precomputation responsibilities from the main
    logits processor class. It provides methods to:

    - Pre-compute commonly used token IDs (digits, notes, sharps/flats, etc.)
    - Identify and cache audio code token IDs from the vocabulary
    - Extract audio code values from individual token IDs
    - Build precomputed mask tensors for O(1) token blocking
    - Apply whitelist constraints efficiently in-place

    Assumes the host class provides ``self.tokenizer`` and ``self.debug`` attributes.
    """

    def _precompute_tokens(self):
        """Pre-compute commonly used token IDs for efficiency."""
        # Digit tokens (0-9)
        self.digit_tokens = {}
        for d in range(10):
            tokens = self.tokenizer.encode(str(d), add_special_tokens=False)
            if tokens:
                self.digit_tokens[d] = tokens[-1]  # Take last token (in case of prefix)

        # Newline token
        newline_tokens = self.tokenizer.encode("\n", add_special_tokens=False)
        self.newline_token = newline_tokens[-1] if newline_tokens else None

        # Note tokens for keyscale (A-G)
        self.note_tokens = {}
        for note in KEYSCALE_NOTES:
            tokens = self.tokenizer.encode(note, add_special_tokens=False)
            if tokens:
                self.note_tokens[note] = tokens[-1]

        # Sharp/flat tokens
        self.sharp_tokens = []
        for s in ["#", "♯"]:
            tokens = self.tokenizer.encode(s, add_special_tokens=False)
            if tokens:
                self.sharp_tokens.append(tokens[-1])

        self.flat_tokens = []
        for f in ["b", "♭"]:
            tokens = self.tokenizer.encode(f, add_special_tokens=False)
            if tokens:
                self.flat_tokens.append(tokens[-1])

        # Space token
        space_tokens = self.tokenizer.encode(" ", add_special_tokens=False)
        self.space_token = space_tokens[-1] if space_tokens else None

        # Major/minor tokens (we'll encode the full words)
        self.major_start_tokens = []
        self.minor_start_tokens = []
        for prefix in ["m", "M"]:
            tokens = self.tokenizer.encode(prefix, add_special_tokens=False)
            if tokens:
                if prefix.lower() == "m":
                    self.minor_start_tokens.append(tokens[-1])
                    self.major_start_tokens.append(tokens[-1])  # "major" also starts with m

        # Vocab size
        self.vocab_size = len(self.tokenizer)

        # Comma token for multi-genre support
        comma_tokens = self.tokenizer.encode(",", add_special_tokens=False)
        self.comma_token = comma_tokens[-1] if comma_tokens else None

        # EOS token for duration-constrained codes generation
        self.eos_token_id = self.tokenizer.eos_token_id

        # Period token for caption field transition logic
        period_tokens = self.tokenizer.encode(".", add_special_tokens=False)
        self.period_token = period_tokens[-1] if period_tokens else None

        # Backtick tokens for blocking code blocks in caption
        backtick_tokens = self.tokenizer.encode("`", add_special_tokens=False)
        self.backtick_token = backtick_tokens[-1] if backtick_tokens else None

        # Valid language codes (ISO 639-1 and common variants)
        self.valid_languages = VALID_LANGUAGES

        # Precompute audio code token IDs (tokens matching <|audio_code_\d+|>)
        # These should be blocked during caption generation
        self.audio_code_token_ids: Set[int] = set()
        self._precompute_audio_code_tokens()

        # Precompute audio code mask for efficient blocking (O(1) instead of O(n))
        # This mask will be added to scores during caption generation
        self.audio_code_mask: Optional[torch.Tensor] = None
        # Inverse mask: block all non-audio-code tokens (for CODES_GENERATION state)
        self.non_audio_code_mask: Optional[torch.Tensor] = None
        self._build_audio_code_mask()

        # Build valid keyscales set (prefix tree will be built after _char_to_tokens is initialized)
        # 7 notes × 5 accidentals (none, #, b, ♯, ♭) × 2 modes = 70 valid combinations
        self.valid_keyscales = VALID_KEYSCALES.copy()

        # keyscale_prefix_tree will be built in _precompute_char_token_mapping() after _char_to_tokens is ready
        # Numeric prefix trees will be built after field_specs is defined

    def _precompute_audio_code_tokens(self):
        """
        Precompute audio code token IDs (tokens matching <|audio_code_\\d+|>).
        These tokens should be blocked during caption generation.
        Only tokens with code values in range [0, MAX_AUDIO_CODE] are included.
        """
        import re
        audio_code_pattern = re.compile(r'^<\|audio_code_(\d+)\|>$')
        invalid_tokens_count = 0

        # Iterate through vocabulary to find audio code tokens
        for token_id in range(self.vocab_size):
            try:
                token_text = self.tokenizer.decode([token_id])
                match = audio_code_pattern.match(token_text)
                if match:
                    # Extract code value from token text
                    code_value = int(match.group(1))
                    # Only add tokens with valid code values (0-63999)
                    if 0 <= code_value <= MAX_AUDIO_CODE:
                        self.audio_code_token_ids.add(token_id)
                    else:
                        invalid_tokens_count += 1
                        if self.debug:
                            logger.debug(f"Skipping audio code token {token_id} with invalid code value {code_value} (max: {MAX_AUDIO_CODE})")
            except Exception:
                continue

        if invalid_tokens_count > 0:
            logger.debug(f"Found {invalid_tokens_count} audio code tokens with values outside valid range [0, {MAX_AUDIO_CODE}]")

        # Log warning if no valid tokens found (this would prevent code generation)
        if len(self.audio_code_token_ids) == 0:
            logger.warning(f"No valid audio code tokens found in vocabulary (range [0, {MAX_AUDIO_CODE}]). Code generation may fail.")
        elif self.debug:
            logger.debug(f"Found {len(self.audio_code_token_ids)} valid audio code tokens (range [0, {MAX_AUDIO_CODE}])")

    def _extract_code_from_token(self, token_id: int) -> Optional[int]:
        """
        Extract audio code value from a token ID.

        Args:
            token_id: Token ID to extract code value from

        Returns:
            Code value if token is a valid audio code token, None otherwise
        """
        import re
        audio_code_pattern = re.compile(r'^<\|audio_code_(\d+)\|>$')

        try:
            token_text = self.tokenizer.decode([token_id])
            match = audio_code_pattern.match(token_text)
            if match:
                return int(match.group(1))
        except Exception:
            pass

        return None

    def _build_audio_code_mask(self):
        """
        Build a precomputed mask tensor for blocking audio code tokens.
        This mask can be added to scores in O(1) time instead of O(n) loop.

        The mask is [1, vocab_size] tensor with -inf at audio code token positions.

        Also builds the inverse mask (non_audio_code_mask) for CODES_GENERATION state,
        which blocks all non-audio-code tokens.
        """
        if not self.audio_code_token_ids:
            self.audio_code_mask = None
            self.non_audio_code_mask = None
            return

        # Create mask tensor: 0 everywhere, -inf at audio code positions
        # Use float32 for compatibility with most model dtypes
        mask = torch.zeros(1, self.vocab_size, dtype=torch.float32)

        # Convert set to list for indexing
        audio_code_indices = list(self.audio_code_token_ids)

        # Set -inf at audio code token positions
        mask[0, audio_code_indices] = float('-inf')

        self.audio_code_mask = mask

        # Build inverse mask: -inf everywhere EXCEPT at audio code positions
        # This is used in CODES_GENERATION state to only allow audio codes
        inverse_mask = torch.full((1, self.vocab_size), float('-inf'), dtype=torch.float32)
        inverse_mask[0, audio_code_indices] = 0

        # Also allow EOS token in codes generation (will be controlled by duration constraint)
        if self.eos_token_id is not None:
            inverse_mask[0, self.eos_token_id] = 0

        self.non_audio_code_mask = inverse_mask

        if self.debug:
            logger.debug(f"Built audio code masks for {len(self.audio_code_token_ids)} tokens")

    def _apply_whitelist_inplace(self, scores: torch.Tensor, allowed_tokens: List[int]) -> None:
        """
        Apply whitelist constraint inplace: only allow specified tokens, block all others.

        This is more efficient than creating a mask tensor because:
        1. No memory allocation for mask
        2. No tensor addition operation

        Args:
            scores: [1, vocab_size] scores tensor to modify inplace
            allowed_tokens: List of token IDs to allow (all others will be set to -inf)
        """
        if not allowed_tokens:
            # No tokens allowed, set all to -inf
            scores.fill_(float('-inf'))
            return

        # Save the original values of allowed tokens
        allowed_indices = torch.tensor(allowed_tokens, device=scores.device, dtype=torch.long)
        saved_values = scores[0, allowed_indices].clone()

        # Set all scores to -inf
        scores.fill_(float('-inf'))

        # Restore allowed token values
        scores[0, allowed_indices] = saved_values
