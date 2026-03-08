
"""
Constrained Logits Processor for ACE-Step Language Model

This module implements a finite state machine (FSM) based logits processor that constrains
the language model's output to follow specific formats and value ranges during music generation.

Key Features:
- Enforces structured metadata generation (BPM, duration, keyscale, etc.)
- Validates numeric ranges (BPM: 30-300, Duration: 10-600s)
- Ensures proper formatting for musical metadata
- Prevents generation of invalid tokens or formats
- Supports constrained audio code generation (0-63999)

The FSM guides the model through different states to ensure outputs conform to expected
schema requirements without post-processing corrections.

Usage:
    processor = ConstrainedLogitsProcessor(tokenizer, mode="metadata")
    outputs = model.generate(inputs, logits_processor=[processor])
"""

from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple
from loguru import logger
from transformers import AutoTokenizer
from transformers.generation.logits_process import LogitsProcessor
import os
import torch
from acestep.constants import (
    BPM_MIN,
    BPM_MAX,
    DURATION_MIN,
    DURATION_MAX,
    VALID_TIME_SIGNATURES,
)
from acestep.constrained_decoding.token_precompute import TokenPrecomputeMixin
from acestep.constrained_decoding.trie_builders import TrieBuildersMixin
from acestep.constrained_decoding.genres import GenresMixin


# ==============================================================================
# FSM States for Constrained Decoding
# ==============================================================================
class FSMState(Enum):
    """Finite State Machine states for metadata generation"""
    THINK_TAG = auto()           # Generating "<think>"
    NEWLINE_AFTER_THINK = auto() # Generating "\n" after <think>
    BPM_NAME = auto()            # Generating "bpm: "
    BPM_VALUE = auto()           # Generating numeric value 30-300
    NEWLINE_AFTER_BPM = auto()   # Generating "\n" after bpm value
    CAPTION_NAME = auto()        # Generating "caption: "
    CAPTION_VALUE = auto()       # Generating caption text (no code blocks/newlines)
    DURATION_NAME = auto()       # Generating "duration: "
    DURATION_VALUE = auto()      # Generating numeric value 10-600
    NEWLINE_AFTER_DURATION = auto()
    GENRES_NAME = auto()         # Generating "genres: "
    GENRES_VALUE = auto()        # Generating any non-empty string
    NEWLINE_AFTER_GENRES = auto()
    KEYSCALE_NAME = auto()       # Generating "keyscale: "
    KEYSCALE_VALUE = auto()      # Generating keyscale pattern
    NEWLINE_AFTER_KEYSCALE = auto()
    LANGUAGE_NAME = auto()       # Generating "language: "
    LANGUAGE_VALUE = auto()      # Generating language code (en, zh, ja, etc.)
    TIMESIG_NAME = auto()        # Generating "timesignature: "
    TIMESIG_VALUE = auto()       # Generating 2, 3, 4, or 6
    NEWLINE_AFTER_TIMESIG = auto()
    THINK_END_TAG = auto()       # Generating "</think>"
    CODES_GENERATION = auto()    # Generating audio codes (no constraints)
    COMPLETED = auto()           # Generation completed


class MetadataConstrainedLogitsProcessor(
    TokenPrecomputeMixin,
    TrieBuildersMixin,
    GenresMixin,
    LogitsProcessor,
):
    """
    FSM-driven LogitsProcessor that constrains generation to produce valid metadata.
    
    This processor enforces the following format:
    <think>
    bpm: [30-300]
    caption: [text without code blocks, ends with period + newline]
    duration: [10-600]
    keyscale: [A-G][#/♭]? [major/minor]
    language: [en/zh/ja/ko/es/fr/de/uk/ru/...]
    timesignature: [2/3/4/6]
    </think>
    
    It uses token masking (setting invalid token logits to -inf) to enforce constraints.
    For numeric fields, it uses early-blocking to prevent out-of-range values.
    For field transitions (e.g., end of numeric value), it compares P(newline) vs P(digit).
    For caption field, it blocks code blocks and newlines, and only transitions when
    the previous token was a period and newline has the highest probability.
    """
    
    def __init__(
        self,
        tokenizer: AutoTokenizer,
        enabled: bool = True,
        debug: bool = False,
        genres_vocab_path: Optional[str] = None,
        skip_genres: bool = True,
        max_duration: Optional[int] = None,
    ):
        """
        Initialize the constrained logits processor.
        
        This processor should be initialized once when loading the LLM and reused
        for all generations.
        Args:
            tokenizer: The tokenizer to use for encoding/decoding
            enabled: Whether to enable constrained decoding
            debug: Whether to print debug information
            genres_vocab_path: Path to genres vocabulary file
            skip_genres: Whether to skip genres field generation
            max_duration: Maximum duration in seconds (default: DURATION_MAX from constants)
        """
        self.tokenizer = tokenizer
        self.enabled = enabled
        self.debug = debug
        self.skip_genres = skip_genres
        
        # Maximum duration limit (can be dynamically updated based on GPU config)
        self.max_duration = max_duration if max_duration is not None else DURATION_MAX
        self.skip_caption = False  # Set to True to skip caption field generation
        self.skip_language = False  # Set to True to skip language field generation
        self.caption: Optional[str] = None  # Set via update_caption() before each generation
        
        # User-provided metadata fields (optional)
        # If provided, these fields will be used directly instead of generating
        # Format: {"bpm": "120", "caption": "...", "duration": "234", "keyscale": "G major", "language": "en", "timesignature": "4"}
        self.user_provided_metadata: Dict[str, Optional[str]] = {
            "bpm": None,
            "caption": None,
            "duration": None,
            "keyscale": None,
            "language": None,
            "timesignature": None,
            "genres": None,
        }
        
        # Temperature settings for different generation phases (set per-generation)
        # If set, the processor will apply temperature scaling (divide logits by temperature)
        # Note: Set base sampler temperature to 1.0 when using processor-based temperature
        self.metadata_temperature: Optional[float] = None
        self.codes_temperature: Optional[float] = None
        
        # Duration constraint for codes generation
        # 5 codes = 1 second, so target_codes = target_duration * 5
        self.target_duration: Optional[float] = None  # User-specified duration in seconds
        self.target_codes: Optional[int] = None  # Computed target codes count
        self.codes_count: int = 0  # Counter for generated codes
        
        # Stop at reasoning flag - if True, stop generation after </think> tag
        self.stop_at_reasoning: bool = False
        
        # Generation phase - "cot" or "codes"
        # Used to determine FSM behavior when prompt already contains CoT
        self.generation_phase: str = "cot"
        
        # Current state
        self.state = FSMState.THINK_TAG
        self.position_in_state = 0  # Position within current state's fixed string
        self.accumulated_value = ""  # For numeric/text value accumulation (legacy, for compatibility)
        self.accumulated_token_ids: List[int] = []  # Token ID sequence for keyscale (and other fields)
        
        # Caption generation state tracking
        self.caption_after_newline = False  # Track if we're right after a newline in caption
        self.caption_token_count = 0  # Track token count for caption (max 512)
        self.caption_ending = False  # Track if caption is ending (after detecting non-indented line)
        self.pending_field_name = ""  # Accumulate field name tokens when caption is ending
        
        # Token queue for user-provided fields (injected directly without generation)
        self.user_field_token_queue: List[int] = []
        self.current_user_field: Optional[str] = None  # Current field being injected
        
        # Pre-compute token IDs for efficiency
        self._precompute_tokens()

        # Genres vocabulary for constrained decoding
        self.genres_vocab_path = genres_vocab_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "genres_vocab.txt"
        )
        self.genres_vocab: List[str] = []  # Full vocab
        self.genres_vocab_mtime: float = 0.0
        self.genres_trie: Dict = {}  # Trie for full vocab (fallback)
        self.caption_genres_trie: Dict = {}  # Trie for caption-matched genres (priority)
        self.caption_matched_genres: List[str] = []  # Genres matched from caption
        
        self._char_to_tokens: Dict[str, set] = {}  # Precomputed char -> token IDs mapping
        
        # Precompute token mappings once (O(vocab_size), runs once at init)
        self._precompute_char_token_mapping()
        
        # Field definitions (needed before building prefix trees)
        # Note: duration max uses self.max_duration which can be dynamically updated based on GPU config
        self.field_specs = {
            "bpm": {"min": BPM_MIN, "max": BPM_MAX},
            "duration": {"min": DURATION_MIN, "max": self.max_duration},
            "timesignature": {"valid_values": VALID_TIME_SIGNATURES},
        }
        
        # Build valid numeric values for BPM, Duration, Timesignature
        # These will be used to build prefix trees based on actual tokenization
        self.valid_bpm_values = [str(v) for v in range(self.field_specs["bpm"]["min"], self.field_specs["bpm"]["max"] + 1)]
        self.valid_duration_values = [str(v) for v in range(self.field_specs["duration"]["min"], self.field_specs["duration"]["max"] + 1)]
        self.valid_timesig_values = [str(v) for v in self.field_specs["timesignature"]["valid_values"]]
        
        # Build keyscale prefix tree (requires _char_to_tokens to be initialized)
        self.keyscale_prefix_tree = self._build_keyscale_prefix_tree()
        
        # Build numeric prefix trees (BPM, Duration, Timesignature) with context
        # IMPORTANT: State machine generates "bpm:" (no space), but tokenizer sees "bpm: " (with space)
        # Use same logic as keyscale: context_prefix_for_matching (no space) and context_prefix_for_tokenization (with space)
        self.bpm_prefix_tree = self._build_numeric_prefix_tree(
            self.valid_bpm_values, 
            context_prefix_for_matching="bpm:",
            context_prefix_for_tokenization="bpm: "
        )
        self.duration_prefix_tree = self._build_numeric_prefix_tree(
            self.valid_duration_values,
            context_prefix_for_matching="duration:",
            context_prefix_for_tokenization="duration: "
        )
        self.timesig_prefix_tree = self._build_numeric_prefix_tree(
            self.valid_timesig_values,
            context_prefix_for_matching="timesignature:",
            context_prefix_for_tokenization="timesignature: "
        )
        
        # Build language prefix tree (similar to keyscale but for language codes)
        self.language_prefix_tree = self._build_language_prefix_tree()

        self._load_genres_vocab()
        
        # Fixed strings for each state
        # IMPORTANT: Do NOT include trailing space after colon - tokenizer will handle spacing
        # All matching should be done at token level, not string level
        # NOTE: NEWLINE_AFTER_* states are removed - field values generate newline directly and transition to next field
        self.fixed_strings = {
            FSMState.THINK_TAG: "<think>",
            FSMState.NEWLINE_AFTER_THINK: "\n",
            FSMState.BPM_NAME: "bpm:",
            FSMState.CAPTION_NAME: "caption:",
            FSMState.DURATION_NAME: "duration:",
            FSMState.GENRES_NAME: "genres:",
            FSMState.KEYSCALE_NAME: "keyscale:",
            FSMState.LANGUAGE_NAME: "language:",
            FSMState.TIMESIG_NAME: "timesignature:",
            FSMState.THINK_END_TAG: "</think>",
        }
        
        # State transitions
        self._build_state_transitions()
    
    def _get_next_field_state(self, current_field: str) -> Optional[FSMState]:
        """
        Get the next field state. Always returns the next field's NAME state,
        even if the field is user-provided (we still need to generate the field name).
        
        Args:
            current_field: Current field name ("bpm", "caption", "duration", "genres", "keyscale", "language", "timesignature")
            
        Returns:
            Next FSMState (NAME state of next field), or THINK_END_TAG if no more fields
        """
        # New field order: bpm -> caption -> duration -> keyscale -> language -> timesignature
        # genres is optional and can be skipped
        field_order = ["bpm", "caption", "duration", "genres", "keyscale", "language", "timesignature"]
        field_to_state = {
            "bpm": FSMState.BPM_NAME,
            "caption": FSMState.CAPTION_NAME,
            "duration": FSMState.DURATION_NAME,
            "genres": FSMState.GENRES_NAME,
            "keyscale": FSMState.KEYSCALE_NAME,
            "language": FSMState.LANGUAGE_NAME,
            "timesignature": FSMState.TIMESIG_NAME,
        }
        
        try:
            current_idx = field_order.index(current_field)
        except ValueError:
            return FSMState.THINK_END_TAG
        
        # Find next field in order
        for i in range(current_idx + 1, len(field_order)):
            field = field_order[i]
            
            # Skip fields based on flags
            if field == "genres" and self.skip_genres:
                continue
            if field == "caption" and self.skip_caption:
                continue
            if field == "language" and self.skip_language:
                continue
            
            # Return the next field's NAME state (even if user-provided, we still generate field name)
            return field_to_state[field]
        
        # No more fields, go to THINK_END_TAG
        return FSMState.THINK_END_TAG
    
    def _build_state_transitions(self):
        """Build state transition map based on user-provided metadata."""
        self.next_state = {
            FSMState.THINK_TAG: FSMState.NEWLINE_AFTER_THINK,
            FSMState.NEWLINE_AFTER_THINK: FSMState.BPM_NAME,  # Always start with BPM
            FSMState.THINK_END_TAG: FSMState.CODES_GENERATION,
            FSMState.CODES_GENERATION: FSMState.COMPLETED,
        }
        
        # Build transitions for all fields (even if user-provided, we still need to generate field name)
        # Field order: bpm -> caption -> duration -> genres -> keyscale -> language -> timesignature
        
        # BPM field: NAME -> VALUE -> next field (caption or duration)
        self.next_state[FSMState.BPM_NAME] = FSMState.BPM_VALUE
        self.next_state[FSMState.BPM_VALUE] = self._get_next_field_state("bpm")
        
        # Caption field (only if not skipped): NAME -> VALUE -> next field (duration)
        if not self.skip_caption:
            self.next_state[FSMState.CAPTION_NAME] = FSMState.CAPTION_VALUE
            self.next_state[FSMState.CAPTION_VALUE] = self._get_next_field_state("caption")
        
        # Duration field: NAME -> VALUE -> next field
        self.next_state[FSMState.DURATION_NAME] = FSMState.DURATION_VALUE
        self.next_state[FSMState.DURATION_VALUE] = self._get_next_field_state("duration")

        # Genres field (only if not skipped): NAME -> VALUE -> next field
        if not self.skip_genres:
            self.next_state[FSMState.GENRES_NAME] = FSMState.GENRES_VALUE
            self.next_state[FSMState.GENRES_VALUE] = self._get_next_field_state("genres")
        
        # Keyscale field: NAME -> VALUE -> next field (language or timesignature)
        self.next_state[FSMState.KEYSCALE_NAME] = FSMState.KEYSCALE_VALUE
        self.next_state[FSMState.KEYSCALE_VALUE] = self._get_next_field_state("keyscale")
        
        # Language field (only if not skipped): NAME -> VALUE -> next field (timesignature)
        if not self.skip_language:
            self.next_state[FSMState.LANGUAGE_NAME] = FSMState.LANGUAGE_VALUE
            self.next_state[FSMState.LANGUAGE_VALUE] = self._get_next_field_state("language")
        
        # Timesignature field: NAME -> VALUE -> THINK_END_TAG
        self.next_state[FSMState.TIMESIG_NAME] = FSMState.TIMESIG_VALUE
        self.next_state[FSMState.TIMESIG_VALUE] = FSMState.THINK_END_TAG

    def set_skip_genres(self, skip: bool):
        """Set whether to skip genres generation and rebuild state transitions."""
        self.skip_genres = skip
        self._build_state_transitions()
    
    def set_skip_caption(self, skip: bool):
        """Set whether to skip caption generation and rebuild state transitions."""
        self.skip_caption = skip
        self._build_state_transitions()
    
    def set_skip_language(self, skip: bool):
        """Set whether to skip language generation and rebuild state transitions."""
        self.skip_language = skip
        self._build_state_transitions()
    
    @staticmethod
    def postprocess_caption(caption: str) -> str:
        """
        Post-process caption to remove YAML multi-line formatting.
        Converts YAML-style multi-line text (with newlines and leading spaces) 
        to a single-line string.
        
        Example:
            Input:  "An emotional ballad.\\n  The track opens with piano.\\n  More text."
            Output: "An emotional ballad. The track opens with piano. More text."
        
        Args:
            caption: Raw caption text with possible YAML formatting
            
        Returns:
            Clean single-line caption
        """
        if not caption:
            return caption
        
        # Split by newlines
        lines = caption.split('\n')
        
        # Process each line: strip leading/trailing whitespace
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)
        
        # Join with single space
        return ' '.join(cleaned_lines)
    
    def set_stop_at_reasoning(self, stop: bool):
        """
        Set whether to stop generation after </think> tag.
        
        Args:
            stop: If True, generation will stop immediately after </think> tag is generated.
                  If False, generation continues to codes generation phase.
        """
        self.stop_at_reasoning = stop
    
    def set_generation_phase(self, phase: str):
        """
        Set the generation phase.
        
        Args:
            phase: "cot" for CoT metadata generation, "codes" for audio codes generation,
                   or "understand" for audio understanding (codes → metadata + lyrics).
                   When phase is "codes" and the input prompt already contains </think>,
                   the FSM will skip metadata generation and go directly to codes generation.
                   When phase is "understand", generate CoT metadata then free-form lyrics.
        """
        if phase not in ("cot", "codes", "understand"):
            raise ValueError(f"Invalid generation phase: {phase!r}. Must be 'cot', 'codes', or 'understand'")
        self.generation_phase = phase
    
    def set_user_metadata(self, metadata: Optional[Dict[str, Optional[str]]] = None):
        """
        Set user-provided metadata fields. Fields that are provided will be used directly
        instead of generating. Fields that are None will be generated.
        
        Args:
            metadata: Dictionary with optional fields:
                - "bpm": Optional[str] - e.g., "120"
                - "caption": Optional[str] - e.g., "A melodic piano piece..."
                - "duration": Optional[str] - e.g., "234"
                - "keyscale": Optional[str] - e.g., "G major"
                - "language": Optional[str] - e.g., "en"
                - "timesignature": Optional[str] - e.g., "4"
                - "genres": Optional[str] - e.g., "Pop Rock"
                If None, clears all user-provided metadata.
        """
        if metadata is None:
            metadata = {}
        
        # Update user-provided metadata
        for field in ["bpm", "caption", "duration", "keyscale", "language", "timesignature", "genres"]:
            if field in metadata:
                self.user_provided_metadata[field] = metadata[field]
            else:
                self.user_provided_metadata[field] = None
        
        # Rebuild state transitions to skip provided fields
        self._build_state_transitions()
        
        if self.debug:
            provided_fields = [k for k, v in self.user_provided_metadata.items() if v is not None]
            if provided_fields:
                logger.debug(f"User provided metadata fields: {provided_fields}")
            else:
                logger.debug("No user-provided metadata, all fields will be generated")
    
    def reset(self):
        """Reset the processor state for a new generation."""
        self.state = FSMState.THINK_TAG
        self.position_in_state = 0
        self.accumulated_value = ""  # Legacy, kept for compatibility
        self.accumulated_token_ids = []  # Reset token ID sequence
        self.codes_count = 0  # Reset codes counter
        self.user_field_token_queue = []  # Reset user field token queue
        self.current_user_field = None  # Reset current user field
        self.caption_after_newline = False  # Reset caption newline tracking
        self.caption_token_count = 0  # Reset caption token count
        self.caption_ending = False  # Reset caption ending tracking
        self.pending_field_name = ""  # Reset pending field name
    
    def set_target_duration(self, duration: Optional[float]):
        """
        Set the target duration for codes generation.
        
        Args:
            duration: Target duration in seconds. If None, no duration constraint is applied.
                     5 codes = 1 second, so target_codes = duration * 5.
        """
        self.target_duration = duration
        if duration is not None and duration > 0:
            self.target_codes = int(duration * 5)
            if self.debug:
                logger.debug(f"Set target duration: {duration}s -> {self.target_codes} codes")
        else:
            self.target_codes = None
            if self.debug:
                logger.debug("Target duration cleared, no duration constraint")
    
    def set_max_duration(self, max_duration: int):
        """
        Dynamically update the maximum allowed duration for constrained decoding.
        
        This method should be called when GPU configuration changes (e.g., LM initialization state changes).
        It rebuilds the duration prefix tree to constrain duration values to the new maximum.
        
        Args:
            max_duration: Maximum duration in seconds (e.g., 120 for 2 minutes, 360 for 6 minutes)
        """
        if max_duration == self.max_duration:
            return  # No change needed
        
        old_max = self.max_duration
        self.max_duration = max_duration
        
        # Update field specs
        self.field_specs["duration"]["max"] = max_duration
        
        # Rebuild valid duration values
        self.valid_duration_values = [str(v) for v in range(self.field_specs["duration"]["min"], self.field_specs["duration"]["max"] + 1)]
        
        # Rebuild duration prefix tree
        self.duration_prefix_tree = self._build_numeric_prefix_tree(
            self.valid_duration_values,
            context_prefix_for_matching="duration:",
            context_prefix_for_tokenization="duration: "
        )
        
        if self.debug:
            logger.debug(f"Updated max duration: {old_max}s -> {max_duration}s, rebuilt prefix tree with {len(self.valid_duration_values)} values")
    
    def _get_allowed_tokens_for_fixed_string(self, fixed_str: str) -> List[int]:
        """
        Get the token IDs that can continue the fixed string from current position.
        Returns list of allowed token IDs.
        
        Strategy: Find the longest prefix that encodes to a single token, and return that token.
        This ensures we generate by tokens, not character-by-character.
        """
        remaining = fixed_str[self.position_in_state:]
        if not remaining:
            return []
        
        if self.debug:
            logger.debug(f"_get_allowed_tokens_for_fixed_string: fixed_str={repr(fixed_str)}, position_in_state={self.position_in_state}, remaining={repr(remaining)}")
        
        # Try encoding progressively longer prefixes, from longest to shortest
        # We want to find the longest prefix that encodes to a single token
        best_token = None
        best_prefix_len = 0
        
        # First pass: find the longest prefix that encodes to exactly one token
        for end in range(len(remaining), 0, -1):  # Start from longest prefix
            prefix = remaining[:end]
            tokens = self.tokenizer.encode(prefix, add_special_tokens=False)
            if tokens and len(tokens) == 1:
                # Found a prefix that encodes to a single token
                # Use this one (longest match)
                best_token = tokens[0]
                best_prefix_len = end
                if self.debug:
                    logger.debug(f"Found single-token match: prefix={repr(prefix)}, token_id={best_token}, token_text={repr(self.tokenizer.decode([best_token]))}")
                break
        
        # If we found a single-token match, return it (this is the preferred case)
        if best_token is not None:
            return [best_token]
        
        # Fallback: if no single-token match found, collect all possible first tokens
        # This handles edge cases where the string might need multiple tokens
        # But we still want to prefer longer matches
        # IMPORTANT: Only consider tokens that actually match the beginning of remaining string
        # Decode each candidate token and verify it matches the prefix
        allowed_tokens = {}
        for end in range(1, min(len(remaining) + 1, 20)):  # Limit search to avoid too many iterations
            prefix = remaining[:end]
            tokens = self.tokenizer.encode(prefix, add_special_tokens=False)
            if tokens:
                first_token = tokens[0]
                # Verify: decode the token and check it matches the prefix start
                decoded_token = self.tokenizer.decode([first_token])
                # Normalize both for comparison (strip and lower)
                normalized_prefix = prefix.lstrip().lower()
                normalized_decoded = decoded_token.lstrip().lower()
                
                # Check if decoded token matches the prefix start (allowing for space prefixes)
                if normalized_decoded.startswith(normalized_prefix) or normalized_prefix.startswith(normalized_decoded):
                    # Store the longest prefix length for each token
                    if first_token not in allowed_tokens or end > allowed_tokens[first_token]:
                        allowed_tokens[first_token] = end
        
        # Return tokens sorted by prefix length (longest first)
        # This ensures we prefer longer matches
        sorted_tokens = sorted(allowed_tokens.items(), key=lambda x: x[1], reverse=True)
        result = [token for token, _ in sorted_tokens] if sorted_tokens else []
        
        if self.debug:
            logger.debug(f"Fallback: returning {len(result)} tokens: {[(t, repr(self.tokenizer.decode([t]))) for t in result[:5]]}")
            if result:
                logger.debug(f"Fixed string: {repr(fixed_str)}, position: {self.position_in_state}, remaining: {repr(remaining)}")
        
        return result
    
    def _get_allowed_digit_tokens(self, min_val: int, max_val: int) -> List[int]:
        """
        Get allowed digit tokens based on accumulated value and range constraints.
        Uses early-blocking to prevent out-of-range values.
        """
        if not self.accumulated_value:
            # First digit: determine valid starting digits
            allowed_digits = set()
            for v in range(min_val, max_val + 1):
                allowed_digits.add(int(str(v)[0]))
            return [self.digit_tokens[d] for d in allowed_digits if d in self.digit_tokens]
        
        current = int(self.accumulated_value)
        allowed = []
        
        for d in range(10):
            new_value = int(self.accumulated_value + str(d))
            # Check if this digit could lead to a valid final value
            # A digit is valid if:
            # 1. new_value <= max_val (not already exceeded)
            # 2. new_value could potentially reach >= min_val
            #    (i.e., new_value * 10^k >= min_val for some k >= 0)
            
            if new_value > max_val:
                continue  # Already exceeded max
            
            # Check if we can still reach min_val
            # If new_value is already >= min_val, it's valid
            # If new_value < min_val, we need more digits, but new_value * 10 must not exceed max
            if new_value >= min_val:
                allowed.append(d)
            elif new_value * 10 <= max_val:
                # Can add more digits
                allowed.append(d)
        
        return [self.digit_tokens[d] for d in allowed if d in self.digit_tokens]
    
    def _get_allowed_numeric_tokens(self, prefix_tree: Dict[Tuple[int, ...], Set[int]]) -> List[int]:
        """
        Get allowed tokens for numeric field using the precomputed prefix tree.
        
        IMPORTANT: Uses token ID sequence as key (not string) to avoid tokenization mismatches.
        
        Args:
            prefix_tree: Precomputed prefix tree mapping token ID sequence -> set of allowed token IDs
            
        Returns:
            List of allowed token IDs for current accumulated_token_ids
        """
        token_prefix = tuple(self.accumulated_token_ids)
        
        if token_prefix in prefix_tree:
            return list(prefix_tree[token_prefix])
        
        # No valid continuation found - return empty list
        # The caller will handle this by forcing newline to end the field
        return []
    
    def _should_end_numeric_field(self, logits: torch.Tensor, min_val: int, max_val: int) -> bool:
        """
        Determine if we should end the current numeric field.
        Returns True if P(newline) > P(any valid digit) AND current value is valid.
        """
        if not self.accumulated_value:
            return False
        
        current = int(self.accumulated_value)
        if current < min_val or current > max_val:
            return False  # Can't end yet, value not in range
        
        # Get probabilities
        probs = torch.softmax(logits, dim=-1)
        
        newline_prob = probs[0, self.newline_token].item() if self.newline_token else 0
        
        # Get max probability among valid digit tokens
        allowed_digits = self._get_allowed_digit_tokens(min_val, max_val)
        if not allowed_digits:
            return True  # No more digits possible, must end
        
        max_digit_prob = max(probs[0, t].item() for t in allowed_digits)
        
        if self.debug:
            logger.debug(f"Numeric field decision: newline_prob={newline_prob:.4f}, max_digit_prob={max_digit_prob:.4f}")
        
        return newline_prob > max_digit_prob

    
    def _should_end_text_field(self, logits: torch.Tensor) -> bool:
        """
        Determine if we should end a text field (genres).
        Returns True if P(newline) > P(any other token) AND we have some content.
        """
        if not self.accumulated_value.strip():
            return False  # Need at least some content
        
        probs = torch.softmax(logits, dim=-1)
        newline_prob = probs[0, self.newline_token].item() if self.newline_token else 0
        
        # Get max probability among non-newline tokens
        masked_probs = probs.clone()
        if self.newline_token:
            masked_probs[0, self.newline_token] = 0
        max_other_prob = masked_probs[0].max().item()
        
        return newline_prob > max_other_prob
    
    def _get_allowed_keyscale_tokens(self) -> List[int]:
        """
        Get allowed tokens for keyscale field using the precomputed prefix tree.
        Uses token ID sequence as key (not string) to avoid tokenization mismatches.
        """
        # Use token ID sequence as key
        token_prefix = tuple(self.accumulated_token_ids)
        
        if token_prefix in self.keyscale_prefix_tree:
            return list(self.keyscale_prefix_tree[token_prefix])
        
        # Fallback: if we somehow drifted off (shouldn't happen with constrained decoding),
        # return empty to force newline logic or stop.
        return []
    
    def _is_keyscale_complete(self) -> bool:
        """
        Check if keyscale value is complete and valid.
        Uses token ID sequence to check if current prefix allows newline.
        """
        token_prefix = tuple(self.accumulated_token_ids)
        # If current token sequence prefix is in tree and allows newline, it's complete
        if token_prefix in self.keyscale_prefix_tree:
            return self.newline_token in self.keyscale_prefix_tree[token_prefix]
        return False
    
    def _get_allowed_language_tokens(self) -> List[int]:
        """
        Get allowed tokens for language field using the precomputed prefix tree.
        Uses token ID sequence as key (not string) to avoid tokenization mismatches.
        Similar to keyscale.
        """
        token_prefix = tuple(self.accumulated_token_ids)
        
        if token_prefix in self.language_prefix_tree:
            return list(self.language_prefix_tree[token_prefix])
        
        # Fallback: no valid continuation found
        return []
    
    def _get_allowed_timesig_tokens(self) -> List[int]:
        """
        Get allowed tokens for timesignature field using the precomputed prefix tree.
        Uses token ID sequence as key (not string) to avoid tokenization mismatches.
        """
        token_prefix = tuple(self.accumulated_token_ids)
        
        if token_prefix in self.timesig_prefix_tree:
            return list(self.timesig_prefix_tree[token_prefix])
        
        # No valid continuation found - return empty list
        # The caller will handle this by forcing newline to end the field
        return []
    
    def __call__(
        self,
        input_ids: torch.LongTensor,
        scores: torch.FloatTensor,
    ) -> torch.FloatTensor:
        """
        Apply constrained decoding by modifying logits.
        
        Args:
            input_ids: [batch_size, seq_len] input token IDs
            scores: [batch_size, vocab_size] logits for next token
            
        Returns:
            Modified scores with invalid tokens masked to -inf and temperature scaling applied
        """
        if not self.enabled:
            return self._apply_temperature_scaling(scores)
        
        if self.state == FSMState.COMPLETED:
            # In understanding phase, block audio codes during lyrics generation (COMPLETED state)
            if self.generation_phase == "understand" and self.audio_code_mask is not None:
                # Move mask to same device/dtype as scores if needed
                if self.audio_code_mask.device != scores.device or self.audio_code_mask.dtype != scores.dtype:
                    self.audio_code_mask = self.audio_code_mask.to(device=scores.device, dtype=scores.dtype)
                scores = scores + self.audio_code_mask
            return self._apply_temperature_scaling(scores)
        
        # For codes phase, detect if input already contains </think> and skip to CODES_GENERATION
        if self.generation_phase == "codes" and self.state == FSMState.THINK_TAG:
            # Check if input contains </think> token sequence
            if self._input_contains_think_end_tag(input_ids):
                # Skip metadata generation, go directly to codes generation
                self.state = FSMState.CODES_GENERATION
                self.codes_count = 0
                if self.debug:
                    logger.debug("Codes phase: detected </think> in input, skipping to CODES_GENERATION")
        
        if self.state == FSMState.CODES_GENERATION:
            # Block all non-audio-code tokens (only allow audio codes and EOS)
            # Note: audio_code_token_ids already contains only valid tokens (0-63999 range)
            # because _precompute_audio_code_tokens() filters out invalid tokens during initialization
            if self.non_audio_code_mask is not None:
                # Move mask to same device/dtype as scores if needed
                if self.non_audio_code_mask.device != scores.device or self.non_audio_code_mask.dtype != scores.dtype:
                    self.non_audio_code_mask = self.non_audio_code_mask.to(device=scores.device, dtype=scores.dtype)
                scores = scores + self.non_audio_code_mask
            
            # Apply duration constraint in codes generation phase
            if self.target_codes is not None and self.eos_token_id is not None:
                if self.codes_count < self.target_codes:
                    # Block EOS token until target codes count is reached
                    scores[:, self.eos_token_id] = float('-inf')
                    if self.debug:
                        logger.debug(f"Codes generation: {self.codes_count}/{self.target_codes}, blocking EOS")
                else:
                    # Force EOS token when target codes count is reached - inplace
                    eos_scores = scores[:, self.eos_token_id].clone()
                    scores.fill_(float('-inf'))
                    scores[:, self.eos_token_id] = eos_scores
                    if self.debug:
                        logger.debug(f"Codes generation: {self.codes_count}/{self.target_codes}, forcing EOS")
            return self._apply_temperature_scaling(scores)
        
        batch_size = scores.shape[0]
        
        # Process each sequence in batch
        for b in range(batch_size):
            result = self._process_single_sequence(input_ids[b], scores[b:b+1])
            scores[b] = result[0]  # result is [1, vocab_size], need [vocab_size]
        
        # Apply temperature scaling after constraint masking
        return self._apply_temperature_scaling(scores)
    
    def _input_contains_think_end_tag(self, input_ids: torch.LongTensor) -> bool:
        """
        Check if input contains the </think> closing tag.
        
        Args:
            input_ids: [batch_size, seq_len] input token IDs
            
        Returns:
            True if </think> is found in the input (any sequence in batch)
        """
        # Tokenize </think> to get its token sequence
        think_end_tokens = self.tokenizer.encode("</think>", add_special_tokens=False)
        if not think_end_tokens:
            return False
        
        # Check each sequence in batch
        for b in range(input_ids.shape[0]):
            seq = input_ids[b].tolist()
            # Search for the token sequence in the input
            for i in range(len(seq) - len(think_end_tokens) + 1):
                if seq[i:i+len(think_end_tokens)] == think_end_tokens:
                    return True
        
        return False
    
    def _apply_temperature_scaling(self, scores: torch.FloatTensor) -> torch.FloatTensor:
        """
        Apply temperature scaling based on current generation phase.
        
        Temperature scaling: logits = logits / temperature
        - Lower temperature (< 1.0) makes distribution sharper (more deterministic)
        - Higher temperature (> 1.0) makes distribution flatter (more diverse)
        
        Args:
            scores: [batch_size, vocab_size] logits
            
        Returns:
            Temperature-scaled logits
        """
        # Determine which temperature to use based on current state
        if self.state == FSMState.CODES_GENERATION or self.state == FSMState.COMPLETED:
            temperature = self.codes_temperature
        else:
            temperature = self.metadata_temperature
        
        # If no temperature is set for this phase, return scores unchanged
        if temperature is None:
            return scores
        
        # Avoid division by zero
        if temperature <= 0:
            temperature = 1e-6
        
        # Apply temperature scaling
        return scores / temperature
    
    def _get_user_provided_field_tokens(self, field_name: str) -> Optional[List[int]]:
        """
        Get token sequence for a user-provided field (field_name + value + newline).
        Uses the same tokenization logic as prefix tree building.
        
        Args:
            field_name: Field name ("bpm", "caption", "duration", "keyscale", "language", "timesignature")
            
        Returns:
            List of token IDs for the complete field, or None if field is not provided
        """
        value = self.user_provided_metadata.get(field_name)
        if value is None:
            return None
        
        # Build full field string with space (matching prefix tree tokenization)
        field_to_prefix = {
            "bpm": "bpm: ",
            "caption": "caption: ",
            "duration": "duration: ",
            "keyscale": "keyscale: ",
            "language": "language: ",
            "timesignature": "timesignature: ",
            "genres": "genres: ",
        }
        prefix = field_to_prefix[field_name]
        full_text = f"{prefix}{value}\n"
        
        # Tokenize the full field
        tokens = self.tokenizer.encode(full_text, add_special_tokens=False)
        
        # Extract only the field tokens (skip the prefix tokens that match state machine output)
        # The state machine generates "field_name:" (no space), so we need to match that
        prefix_for_matching = field_name + ":"
        prefix_tokens = self.tokenizer.encode(prefix_for_matching, add_special_tokens=False)
        
        # Find where prefix ends in full tokens
        if len(tokens) >= len(prefix_tokens) and tokens[:len(prefix_tokens)] == prefix_tokens:
            # Return tokens after prefix (field value + newline)
            return tokens[len(prefix_tokens):]
        else:
            # Fallback: return all tokens (shouldn't happen if tokenization is consistent)
            if self.debug:
                logger.warning(f"Could not match prefix tokens for field {field_name}, using all tokens")
            return tokens
    
    def _process_single_sequence(
        self,
        input_ids: torch.LongTensor,
        scores: torch.FloatTensor,
    ) -> torch.FloatTensor:
        """Process a single sequence and return modified scores (inplace when possible)."""
        
        # Check if we have tokens in queue for user-provided field
        # If so, inject the next token directly
        if self.user_field_token_queue:
            next_token = self.user_field_token_queue[0]
            self._apply_whitelist_inplace(scores, [next_token])
            return scores
        
        if self.state in self.fixed_strings:
            # Fixed string state: force specific tokens
            fixed_str = self.fixed_strings[self.state]
            allowed = self._get_allowed_tokens_for_fixed_string(fixed_str)
            
            if allowed:
                # Check if we should stop at reasoning (after </think> tag)
                # This happens when we're about to complete the </think> tag
                if self.state == FSMState.THINK_END_TAG and self.stop_at_reasoning:
                    # Check if the next token would complete the fixed string
                    remaining_chars = len(fixed_str) - self.position_in_state
                    # If remaining is small (<= 10 chars, which is typically 1-2 tokens), force EOS
                    if remaining_chars <= 10:
                        # Force EOS token to stop generation
                        if self.eos_token_id is not None:
                            self._apply_whitelist_inplace(scores, [self.eos_token_id])
                            if self.debug:
                                logger.debug(f"stop_at_reasoning=True: forcing EOS near end of </think> tag (remaining: {remaining_chars} chars)")
                            return scores
                
                # Apply whitelist constraint inplace
                self._apply_whitelist_inplace(scores, allowed)
            else:
                # Position exceeds string, move to next state
                # If stop_at_reasoning is True and we're transitioning from THINK_END_TAG,
                # force EOS before transitioning
                if self.state == FSMState.THINK_END_TAG and self.stop_at_reasoning:
                    # Force EOS token to stop generation
                    if self.eos_token_id is not None:
                        self._apply_whitelist_inplace(scores, [self.eos_token_id])
                        if self.debug:
                            logger.debug(f"stop_at_reasoning=True: forcing EOS after completing </think> tag")
                        return scores
                
                old_state = self.state
                self._transition_to_next_state()
                # Avoid infinite recursion: if we're still in a fixed_strings state, just return scores
                if self.state in self.fixed_strings:
                    # This shouldn't happen, but if it does, just return scores to avoid recursion
                    if self.debug:
                        logger.warning(f"State transition from {old_state.name} to {self.state.name} still in fixed_strings, avoiding recursion")
                    return scores
                # For recursion, reset scores to zero (no constraints from previous state)
                scores.zero_()
                return self._process_single_sequence(input_ids, scores)
        
        elif self.state == FSMState.BPM_VALUE:
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["bpm"] is not None and not self.user_field_token_queue and not self.accumulated_token_ids:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["bpm"]
                # Tokenize " value\n" (space + value + newline) to match actual tokenization
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "bpm"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # Allow valid numeric tokens using prefix tree (supports multi-digit tokens like "120")
            allowed = self._get_allowed_numeric_tokens(self.bpm_prefix_tree)
            
            # Also allow newline if current token sequence prefix allows it
            token_prefix = tuple(self.accumulated_token_ids)
            if token_prefix in self.bpm_prefix_tree and self.newline_token in self.bpm_prefix_tree[token_prefix]:
                allowed = allowed + [self.newline_token]
            
            self._apply_whitelist_inplace(scores, allowed)
        
        elif self.state == FSMState.CAPTION_VALUE:
            # Caption field generation with YAML format support:
            # - Allow newlines and spaces (YAML multi-line formatting)
            # - Block audio codes and backticks
            # - Max 512 tokens
            # - Transition when model wants to generate next field (non-indented line)
            
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["caption"] is not None and not self.user_field_token_queue and not self.accumulated_value:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["caption"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "caption"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # Check if we should transition after a newline (non-indented line = new field)
            if self.caption_after_newline:
                # Get top token from current scores
                top_token_id = torch.argmax(scores[0]).item()
                top_token_text = self.tokenizer.decode([top_token_id])
                
                # If top token does NOT start with space/tab, it's a new field (like "duration:")
                if len(top_token_text) > 0 and top_token_text[0] not in ' \t':
                    # Caption is ending - LM is generating next field name
                    # Instead of forcing state transition to DURATION_NAME (which would regenerate the field name),
                    # we enter a "caption_ending" mode where we allow free generation until we detect the field value
                    self.caption_after_newline = False
                    self.caption_ending = True  # Start tracking field name
                    self.pending_field_name = ""  # Reset pending field name
                    # Allow free generation (no constraints) so LM can generate field name naturally
                    return scores
                else:
                    # It's indentation, continue caption (don't transition!)
                    self.caption_after_newline = False
                    # Continue normal caption generation
                    # Fall through to caption constraints below

            # If caption is ending (LM generating next field name), allow free generation
            # and track the field name until we see colon
            if self.caption_ending:
                # Allow any token (free generation)
                # The field name detection will happen in update_state()
                return scores
            
            # Block backticks (code blocks) - inplace
            if self.backtick_token is not None:
                scores[0, self.backtick_token] = float('-inf')
            
            # Block ALL audio code tokens (critical - these should never appear in caption)
            # Use precomputed mask for O(1) performance instead of O(n) loop
            if self.audio_code_mask is not None:
                # Move mask to same device/dtype as scores if needed
                if self.audio_code_mask.device != scores.device or self.audio_code_mask.dtype != scores.dtype:
                    self.audio_code_mask = self.audio_code_mask.to(device=scores.device, dtype=scores.dtype)
                scores = scores + self.audio_code_mask
            
            # Enforce 512 token limit for caption
            if self.caption_token_count >= 512:
                # Force end by only allowing newline
                if self.newline_token is not None:
                    self._apply_whitelist_inplace(scores, [self.newline_token])
                    return scores
            
            # Allow natural generation (with blocked audio codes and backticks)
            return scores
        
        elif self.state == FSMState.DURATION_VALUE:
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["duration"] is not None and not self.user_field_token_queue and not self.accumulated_token_ids:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["duration"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "duration"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # If target_duration is set, force generate that exact value
            if self.target_duration is not None:
                target_str = str(int(self.target_duration))
                current_pos = len(self.accumulated_value)
                
                if current_pos < len(target_str):
                    # Force the next digit
                    next_digit = int(target_str[current_pos])
                    if next_digit in self.digit_tokens:
                        self._apply_whitelist_inplace(scores, [self.digit_tokens[next_digit]])
                else:
                    # All digits generated, force newline
                    if self.newline_token:
                        self._apply_whitelist_inplace(scores, [self.newline_token])
            else:
                # Normal duration generation with range constraint
                # Allow valid numeric tokens using prefix tree (supports multi-digit tokens like "60", "120")
                allowed = self._get_allowed_numeric_tokens(self.duration_prefix_tree)
                
                # Also allow newline if current token sequence prefix allows it
                token_prefix = tuple(self.accumulated_token_ids)
                if token_prefix in self.duration_prefix_tree and self.newline_token in self.duration_prefix_tree[token_prefix]:
                    allowed = allowed + [self.newline_token]
                
                self._apply_whitelist_inplace(scores, allowed)
        
        elif self.state == FSMState.GENRES_VALUE:
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["genres"] is not None and not self.user_field_token_queue and not self.accumulated_value:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["genres"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "genres"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # Try to hot-reload genres vocab if file has changed
            self._try_reload_genres_vocab()
            
            # Get allowed tokens based on genres vocabulary
            allowed = self._get_allowed_genres_tokens()
            
            if allowed:
                # Use vocabulary-constrained decoding
                self._apply_whitelist_inplace(scores, allowed)
            elif self.genres_vocab:
                # Vocab is loaded but no valid continuation found
                # Force newline to end the field
                if self.newline_token:
                    if self.debug:
                        logger.debug(f"No valid genre continuation for '{self.accumulated_value}', forcing newline")
                    self._apply_whitelist_inplace(scores, [self.newline_token])
            else:
                # Fallback: no vocab loaded, use probability-based ending
                if self._should_end_text_field(scores):
                    if self.newline_token:
                        self._apply_whitelist_inplace(scores, [self.newline_token])
                        self._transition_to_next_state()
                else:
                    # Allow any token except newline if we don't have content yet
                    if not self.accumulated_value.strip():
                        if self.newline_token:
                            scores[0, self.newline_token] = float('-inf')
                    # Otherwise, don't constrain (fallback behavior)
        
        elif self.state == FSMState.KEYSCALE_VALUE:
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["keyscale"] is not None and not self.user_field_token_queue and not self.accumulated_token_ids:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["keyscale"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "keyscale"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # Check if current token sequence is complete (allows newline)
            token_prefix = tuple(self.accumulated_token_ids)
            if token_prefix in self.keyscale_prefix_tree and self.newline_token in self.keyscale_prefix_tree[token_prefix]:
                # Complete keyscale, allow newline
                if self.newline_token:
                    self._apply_whitelist_inplace(scores, [self.newline_token])
            else:
                # Not complete, allow valid continuation tokens
                allowed = self._get_allowed_keyscale_tokens()
                if allowed:
                    self._apply_whitelist_inplace(scores, allowed)
                else:
                    # No valid tokens found - force newline to end field
                    # This handles edge cases where keyscale format is unexpected
                    if self.newline_token:
                        self._apply_whitelist_inplace(scores, [self.newline_token])
        
        elif self.state == FSMState.LANGUAGE_VALUE:
            # Language field: Use top-1 probability language (greedy selection)
            # Unlike other fields, we don't use prefix tree sampling.
            # Instead, we select the highest probability language at the start,
            # then force generate the rest of that language code.
            
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["language"] is not None and not self.user_field_token_queue and not self.accumulated_token_ids:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["language"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "language"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores

            # If we haven't started generating language yet (empty accumulated_token_ids),
            # select the top-1 probability token from all valid first tokens
            if not self.accumulated_token_ids:
                # Get all possible first tokens for all languages
                empty_prefix = tuple()
                if empty_prefix in self.language_prefix_tree:
                    candidate_tokens = list(self.language_prefix_tree[empty_prefix])
                    
                    if candidate_tokens:
                        # Find the token with highest probability (top-1) among candidates
                        # Use tensor indexing to get scores of candidate tokens directly
                        candidate_indices = torch.tensor(candidate_tokens, device=scores.device, dtype=torch.long)
                        candidate_scores = scores[0, candidate_indices]
                        
                        # Get the highest probability token among candidates
                        best_idx = torch.argmax(candidate_scores).item()
                        top_token_id = candidate_tokens[best_idx]
                        
                        # Only allow this top-1 token, block all others
                        self._apply_whitelist_inplace(scores, [top_token_id])
                        
                        if self.debug:
                            top_token_text = self.tokenizer.decode([top_token_id])
                            logger.debug(f"Language field: selected top-1 token {top_token_id} ({repr(top_token_text)}) from {len(candidate_tokens)} candidates")
                    else:
                        # No valid first tokens found - force newline
                        if self.newline_token:
                            self._apply_whitelist_inplace(scores, [self.newline_token])
                else:
                    # Empty prefix not in tree - force newline
                    if self.newline_token:
                        self._apply_whitelist_inplace(scores, [self.newline_token])
            else:
                # We've started generating a language, continue with prefix tree constraints
                # Check if current token sequence is complete (allows newline)
                token_prefix = tuple(self.accumulated_token_ids)
                if token_prefix in self.language_prefix_tree and self.newline_token in self.language_prefix_tree[token_prefix]:
                    # Complete language, allow newline
                    if self.newline_token:
                        self._apply_whitelist_inplace(scores, [self.newline_token])
                else:
                    # Not complete, allow valid continuation tokens
                    allowed = self._get_allowed_language_tokens()
                    if allowed:
                        self._apply_whitelist_inplace(scores, allowed)
                    else:
                        # No valid tokens found - force newline to end field
                        if self.newline_token:
                            self._apply_whitelist_inplace(scores, [self.newline_token])
        
        elif self.state == FSMState.TIMESIG_VALUE:
            # Check if field is user-provided and we haven't started injecting yet
            if self.user_provided_metadata["timesignature"] is not None and not self.user_field_token_queue and not self.accumulated_token_ids:
                # Initialize token queue with field value tokens (value + newline)
                value = self.user_provided_metadata["timesignature"]
                value_text = f" {value}\n"
                value_tokens = self.tokenizer.encode(value_text, add_special_tokens=False)
                if value_tokens:
                    self.user_field_token_queue = value_tokens
                    self.current_user_field = "timesignature"
                    # Inject first token
                    self._apply_whitelist_inplace(scores, [value_tokens[0]])
                    return scores
            
            # Check if current token sequence is complete (allows newline)
            token_prefix = tuple(self.accumulated_token_ids)
            if token_prefix in self.timesig_prefix_tree and self.newline_token in self.timesig_prefix_tree[token_prefix]:
                # Complete value, allow newline
                if self.newline_token:
                    self._apply_whitelist_inplace(scores, [self.newline_token])
            else:
                # Not complete, allow valid continuation tokens
                allowed = self._get_allowed_timesig_tokens()
                self._apply_whitelist_inplace(scores, allowed)
        
        return scores
    
    def _transition_to_next_state(self):
        """Transition to the next FSM state."""
        if self.state in self.next_state:
            old_state = self.state
            next_state = self.next_state[self.state]
            
            # Handle different cases at THINK_END_TAG based on generation phase
            # NOTE: Do NOT override next_state here when stop_at_reasoning=True
            # because we need to transition to the tag state first to generate </think>,
            # then handle stop_at_reasoning in update_state() AFTER the tag is complete
            if old_state == FSMState.THINK_END_TAG:
                if self.generation_phase == "understand":
                    # Understanding mode: allow free-form lyrics after metadata
                    # No more constrained decoding after </think>
                    next_state = FSMState.COMPLETED
                    if self.debug:
                        logger.debug(f"generation_phase='understand': allowing free-form lyrics after </think>")
                # else: default to CODES_GENERATION (for "codes" phase) or respect stop_at_reasoning flag
            
            self.state = next_state
            self.position_in_state = 0
            self.accumulated_value = ""  # Legacy, kept for compatibility
            self.accumulated_token_ids = []  # Reset token ID sequence for new field
            self.caption_after_newline = False  # Reset caption newline tracking
            self.caption_token_count = 0  # Reset caption token count
            self.caption_ending = False  # Reset caption ending tracking
            self.pending_field_name = ""  # Reset pending field name
            if self.debug:
                logger.debug(f"FSM transition: {old_state.name} -> {self.state.name}")
    
    def update_state(self, generated_token_id: int):
        """
        Update internal state after a token has been generated.
        This should be called after each token generation.
        
        Args:
            generated_token_id: The token ID that was just generated
        """
        if not self.enabled:
            return
        
        if self.state == FSMState.COMPLETED:
            return
        
        if self.state == FSMState.CODES_GENERATION:
            # Count generated codes for duration constraint
            self.codes_count += 1
            if self.debug and self.target_codes is not None:
                logger.debug(f"Codes count: {self.codes_count}/{self.target_codes}")
            return
        
        # Handle user-provided field token injection
        if self.user_field_token_queue:
            # Verify the generated token matches the expected token from queue
            expected_token = self.user_field_token_queue[0]
            if generated_token_id != expected_token:
                if self.debug:
                    logger.warning(f"Expected token {expected_token} but got {generated_token_id} for user-provided field {self.current_user_field}")
            
            # Remove consumed token from queue
            self.user_field_token_queue.pop(0)
            
            # If queue is empty, field injection is complete, transition to next state
            if not self.user_field_token_queue:
                if self.debug:
                    logger.debug(f"Completed injection of user-provided field: {self.current_user_field}")
                field_name = self.current_user_field
                self.current_user_field = None
                
                # Transition to next state (skip VALUE state since we already injected everything)
                # The next state should be determined by _get_next_field_state
                next_state = self._get_next_field_state(field_name)
                if next_state:
                    old_state = self.state
                    self.state = next_state
                    self.position_in_state = 0
                    self.accumulated_value = ""
                    self.accumulated_token_ids = []
                    if self.debug:
                        logger.debug(f"FSM transition (after user field injection): {old_state.name} -> {self.state.name}")
                else:
                    # All fields done, go to THINK_END_TAG
                    self._transition_to_next_state()
            return
        
        token_str = self.tokenizer.decode([generated_token_id])
        
        if self.debug:
            logger.debug(f"Generated token: {repr(token_str)} (id={generated_token_id}), state={self.state.name}")
        
        if self.state in self.fixed_strings:
            # Update position in fixed string
            fixed_str = self.fixed_strings[self.state]
            self.position_in_state += len(token_str)
            
            # Check if we've completed the fixed string
            if self.position_in_state >= len(fixed_str):
                # Special handling for THINK_END_TAG with stop_at_reasoning
                if self.state == FSMState.THINK_END_TAG and self.stop_at_reasoning:
                    # </think> tag is complete, now we can stop generation
                    # Force transition to COMPLETED instead of CODES_GENERATION
                    old_state = self.state
                    self.state = FSMState.COMPLETED
                    self.position_in_state = 0
                    self.accumulated_value = ""
                    self.accumulated_token_ids = []
                    if self.debug:
                        logger.debug(f"FSM transition (stop_at_reasoning): {old_state.name} -> {self.state.name}")
                else:
                    self._transition_to_next_state()
        
        elif self.state in [FSMState.BPM_VALUE, FSMState.DURATION_VALUE, FSMState.TIMESIG_VALUE]:
            # Accumulate numeric value using token ID sequence
            if generated_token_id == self.newline_token:
                old_state = self.state
                self._transition_to_next_state()
                # IMPORTANT: After state transition, if new state is a fixed_strings state,
                # we should NOT update position_in_state with the newline token length,
                # because that token belongs to the old state, not the new state.
                # Return early to avoid the fixed_strings update logic below.
                if self.state in self.fixed_strings:
                    return
            else:
                # Add token ID to sequence (for prefix tree lookup)
                self.accumulated_token_ids.append(generated_token_id)
                # Also update legacy accumulated_value for compatibility
                if token_str.strip().isdigit():
                    self.accumulated_value += token_str.strip()

        elif self.state == FSMState.GENRES_VALUE:
            if generated_token_id == self.newline_token:
                # Newline ends the field
                self._transition_to_next_state()
                # IMPORTANT: After state transition, if new state is a fixed_strings state,
                # we should NOT update position_in_state with the newline token length,
                # because that token belongs to the old state, not the new state.
                # Return early to avoid the fixed_strings update logic below.
                if self.state in self.fixed_strings:
                    return
            else:
                # Genres still uses string-based trie, so keep accumulated_value
                self.accumulated_value += token_str
        
        elif self.state == FSMState.CAPTION_VALUE:
            # Track token count for 512 limit
            self.caption_token_count += 1
            
            # Accumulate caption text
            self.accumulated_value += token_str
            
            # Track if this token contains a newline (for transition detection)
            # Token may be '\n' alone or combined with other chars like '.\n'
            if '\n' in token_str:
                # Mark that we need to check next token for field transition
                self.caption_after_newline = True
            else:
                # Not a newline - if we were after newline and this is not space,
                # transition already happened in _process_single_sequence
                self.caption_after_newline = False
            
            # If caption is ending, accumulate field name and detect field completion
            if self.caption_ending:
                self.pending_field_name += token_str
                
                # Check if we've completed a field name (detected colon)
                if ':' in token_str or token_str.strip() == ':':
                    # Extract field name (before colon)
                    field_name_full = self.pending_field_name.strip()
                    # Remove trailing colon if present
                    field_name = field_name_full.rstrip(':').strip().lower()
                    
                    if self.debug:
                        logger.debug(f"Detected field name after caption: {repr(field_name)}")
                    
                    # Map field name to VALUE state
                    field_name_to_value_state = {
                        "duration": FSMState.DURATION_VALUE,
                        "genres": FSMState.GENRES_VALUE,
                        "keyscale": FSMState.KEYSCALE_VALUE,
                        "language": FSMState.LANGUAGE_VALUE,
                        "timesignature": FSMState.TIMESIG_VALUE,
                    }
                    
                    if field_name in field_name_to_value_state:
                        # Transition directly to the field's VALUE state
                        old_state = self.state
                        self.state = field_name_to_value_state[field_name]
                        self.position_in_state = 0
                        self.accumulated_value = ""
                        self.accumulated_token_ids = []
                        self.caption_ending = False
                        self.pending_field_name = ""
                        
                        if self.debug:
                            logger.debug(f"FSM transition (caption ending): {old_state.name} -> {self.state.name}")
                    else:
                        # Unknown field name, force transition to next field
                        if self.debug:
                            logger.warning(f"Unknown field name after caption: {repr(field_name)}, forcing transition")
                        self.caption_ending = False
                        self.pending_field_name = ""
                        self._transition_to_next_state()
        
        elif self.state == FSMState.KEYSCALE_VALUE:
            if generated_token_id == self.newline_token:
                # Newline ends the field
                self._transition_to_next_state()
                # IMPORTANT: After state transition, if new state is a fixed_strings state,
                # we should NOT update position_in_state with the newline token length,
                # because that token belongs to the old state, not the new state.
                # Return early to avoid the fixed_strings update logic below.
                if self.state in self.fixed_strings:
                    return
            else:
                # Add token ID to sequence (for prefix tree lookup)
                self.accumulated_token_ids.append(generated_token_id)
                # Also update legacy accumulated_value for compatibility
                self.accumulated_value += token_str
        
        elif self.state == FSMState.LANGUAGE_VALUE:
            if generated_token_id == self.newline_token:
                # Newline ends the field
                self._transition_to_next_state()
                if self.state in self.fixed_strings:
                    return
            else:
                # Add token ID to sequence (for prefix tree lookup)
                self.accumulated_token_ids.append(generated_token_id)
                # Also update legacy accumulated_value for compatibility
                self.accumulated_value += token_str

