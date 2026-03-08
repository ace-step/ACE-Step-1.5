"""
Trie (prefix tree) builder methods for constrained decoding.

This module provides the TrieBuildersMixin class, which contains methods for
building token-ID-based prefix trees used to constrain language model output
during metadata generation. These prefix trees map token ID sequence prefixes
to sets of allowed next-token IDs, enabling efficient constrained decoding
for keyscale, numeric, and language fields.

Extracted from MetadataConstrainedLogitsProcessor to improve modularity.
"""

from typing import Dict, List, Set, Tuple

from loguru import logger


class TrieBuildersMixin:
    """Mixin providing prefix tree construction methods for MetadataConstrainedLogitsProcessor.

    This mixin builds token-ID-based prefix trees (tries) that map partial
    token sequences to the set of token IDs allowed to follow. The trees
    are used at inference time to constrain the logits so the model can
    only generate valid keyscale names, numeric values, or language codes.

    Expects the consuming class to provide:
        - self.tokenizer: a HuggingFace-compatible tokenizer
        - self.debug: bool flag controlling verbose logging
        - self.newline_token: int or None, the newline token ID
        - self.valid_keyscales: collection of valid keyscale strings
        - self.valid_languages: collection of valid language code strings
        - self.keyscale_prefix_tree: the built keyscale prefix tree (used by diagnose method)
    """

    def _build_keyscale_prefix_tree(self) -> Dict[Tuple[int, ...], Set[int]]:
        """
        Build keyscale prefix to allowed tokens mapping based on ACTUAL tokenization.

        IMPORTANT: Uses token ID sequences as keys, NOT strings, to avoid tokenization mismatches.

        CRITICAL FIX: The tokenizer may merge the context's trailing space into the next token.
        For example:
        - "keyscale: " tokenizes to [10563, 2246, 25, 220] -> ['keys', 'cale', ':', ' ']
        - "keyscale: G major" tokenizes to [10563, 2246, 25, 479, 3598] -> ['keys', 'cale', ':', ' G', ' major']
        The space ' ' (220) is merged into ' G' (479), so we can't use simple slicing.

        Strategy:
        1. For each keyscale (e.g., "G major"), encode the FULL string "keyscale: G major"
        2. Tokenize to get: [10563, 2246, 25, 479, 3598] -> ['keys', 'cale', ':', ' G', ' major']
        3. Find where context prefix ends by matching token sequences (handling space merging)
        4. Extract keyscale value tokens: [479, 3598] (for "G major")
        5. Build prefix tree using token ID sequences as keys

        This ensures we get the exact tokenization that occurs during generation.
        """
        prefix_to_tokens: Dict[Tuple[int, ...], Set[int]] = {}

        # Context prefix that appears before keyscale value
        # IMPORTANT: The state machine generates "keyscale:" (no space), but when tokenizing
        # the full string "keyscale: G major", the tokenizer includes space, so we need to
        # match the actual tokenization behavior.
        #
        # Strategy:
        # 1. Use "keyscale:" (no space) to match the state machine's output
        # 2. But when building prefix tree, use "keyscale: " (with space) + keyscale to match actual tokenization
        context_prefix_for_matching = "keyscale:"  # What state machine generates
        context_prefix_for_tokenization = "keyscale: "  # What tokenizer sees in full string

        # First, tokenize the context (without space) to know its token sequence for matching
        context_token_ids = self.tokenizer.encode(context_prefix_for_matching, add_special_tokens=False)

        if self.debug:
            context_tokens_str = [self.tokenizer.decode([t]) for t in context_token_ids]
            logger.debug(f"Context for matching 'keyscale:' tokenizes to {context_token_ids} -> {context_tokens_str}")

        # For each valid keyscale, encode full string and extract value tokens
        for keyscale in self.valid_keyscales:
            # Step 1: Encode full string "keyscale: {keyscale}" (with space, as tokenizer sees it)
            full_text = context_prefix_for_tokenization + keyscale
            full_token_ids = self.tokenizer.encode(full_text, add_special_tokens=False)

            # Step 2: Find where context ends in full_token_ids
            # We match using context_prefix_for_matching ("keyscale:") token sequence
            # because that's what the state machine actually generates
            context_end_idx = None

            # Try exact prefix match using context_prefix_for_matching token sequence
            if len(full_token_ids) >= len(context_token_ids):
                if full_token_ids[:len(context_token_ids)] == context_token_ids:
                    context_end_idx = len(context_token_ids)

            if context_end_idx is None:
                if self.debug:
                    logger.warning(f"Could not find context prefix in full tokenization of '{full_text}', skipping")
                continue

            # Step 3: Extract keyscale value tokens (everything after context)
            keyscale_token_ids = full_token_ids[context_end_idx:]

            # Step 4: Verify we extracted some tokens (sanity check)
            if not keyscale_token_ids:
                if self.debug:
                    logger.warning(f"No tokens extracted for keyscale '{keyscale}', skipping")
                continue

            # Step 5: Verify first token is a note (A-G)
            # This is critical: the first token of keyscale value must be a note
            first_token_id = keyscale_token_ids[0]
            first_token_str = self.tokenizer.decode([first_token_id])
            # Check if first token starts with a note (A-G, case insensitive, with optional leading space)
            first_char = first_token_str.lstrip()[0].upper() if first_token_str.lstrip() else ""
            if first_char not in "ABCDEFG":
                # This keyscale's first token is not a note - skip it
                if self.debug:
                    logger.debug(f"Skipping keyscale '{keyscale}': first token is '{first_token_str}' (id={first_token_id}), not a note")
                continue

            # Step 6: Build prefix mappings from keyscale value tokens
            # Use token ID sequences as keys (not strings) to avoid tokenization mismatches
            for i in range(len(keyscale_token_ids) + 1):
                # Current token sequence prefix (empty tuple for start)
                token_prefix = tuple(keyscale_token_ids[:i])

                if token_prefix not in prefix_to_tokens:
                    prefix_to_tokens[token_prefix] = set()

                if i < len(keyscale_token_ids):
                    # Add next token as allowed for current prefix
                    next_token_id = keyscale_token_ids[i]
                    prefix_to_tokens[token_prefix].add(next_token_id)
                else:
                    # Complete keyscale should allow newline
                    if self.newline_token:
                        prefix_to_tokens[token_prefix].add(self.newline_token)

        if self.debug:
            logger.debug(f"Built keyscale prefix tree with {len(prefix_to_tokens)} token sequence prefixes")
            # Check empty prefix (start of keyscale value)
            empty_prefix = tuple()
            if empty_prefix in prefix_to_tokens:
                first_tokens = prefix_to_tokens[empty_prefix]
                decoded_first = [(t, repr(self.tokenizer.decode([t]))) for t in sorted(first_tokens)]
                logger.debug(f"First tokens allowed (empty prefix): {decoded_first}")

        return prefix_to_tokens

    def _build_numeric_prefix_tree(
        self,
        valid_values: List[str],
        context_prefix_for_matching: str = "",
        context_prefix_for_tokenization: str = ""
    ) -> Dict[Tuple[int, ...], Set[int]]:
        """
        Build prefix tree for numeric field based on actual tokenization with context.

        IMPORTANT: Uses token ID sequences as keys, NOT strings, to avoid tokenization mismatches.

        Args:
            valid_values: List of valid numeric strings (e.g., ["30", "31", ..., "300"])
            context_prefix_for_matching: Context string that state machine generates (e.g., "bpm:") - no space
            context_prefix_for_tokenization: Context string for tokenization (e.g., "bpm: ") - with space

        Returns:
            Dict mapping token ID sequence prefix -> set of allowed token IDs
        """
        prefix_to_tokens: Dict[Tuple[int, ...], Set[int]] = {}

        # Encode context for matching (what state machine generates, no space)
        context_token_ids = self.tokenizer.encode(context_prefix_for_matching, add_special_tokens=False) if context_prefix_for_matching else []

        # For each valid value, encode it with context and build prefix mappings
        for value_str in valid_values:
            # Encode value WITH context (with space) to match actual tokenization
            full_text = context_prefix_for_tokenization + value_str
            token_ids = self.tokenizer.encode(full_text, add_special_tokens=False)

            # Find where context ends in full_token_ids using context_prefix_for_matching token sequence
            context_end_idx = None
            if len(token_ids) >= len(context_token_ids):
                if token_ids[:len(context_token_ids)] == context_token_ids:
                    context_end_idx = len(context_token_ids)

            if context_end_idx is None:
                if self.debug:
                    logger.warning(f"Could not find context prefix in full tokenization of '{full_text}', skipping")
                continue

            # Extract only tokens that belong to the value itself (skip context tokens)
            value_token_ids = token_ids[context_end_idx:]

            # Build prefix mappings using token ID sequences as keys
            for i in range(len(value_token_ids) + 1):
                # Current token sequence prefix (empty tuple for start)
                token_prefix = tuple(value_token_ids[:i])

                if token_prefix not in prefix_to_tokens:
                    prefix_to_tokens[token_prefix] = set()

                if i < len(value_token_ids):
                    # Add next token as allowed for current prefix
                    next_token_id = value_token_ids[i]
                    prefix_to_tokens[token_prefix].add(next_token_id)
                else:
                    # Complete value should allow newline
                    if self.newline_token:
                        prefix_to_tokens[token_prefix].add(self.newline_token)

        return prefix_to_tokens

    def _build_language_prefix_tree(self) -> Dict[Tuple[int, ...], Set[int]]:
        """
        Build language prefix to allowed tokens mapping based on ACTUAL tokenization.
        Similar to keyscale prefix tree but for language codes.

        Uses token ID sequences as keys, NOT strings, to avoid tokenization mismatches.
        """
        prefix_to_tokens: Dict[Tuple[int, ...], Set[int]] = {}

        context_prefix_for_matching = "language:"
        context_prefix_for_tokenization = "language: "

        context_token_ids = self.tokenizer.encode(context_prefix_for_matching, add_special_tokens=False)

        if self.debug:
            context_tokens_str = [self.tokenizer.decode([t]) for t in context_token_ids]
            logger.debug(f"Context for matching 'language:' tokenizes to {context_token_ids} -> {context_tokens_str}")

        for lang in self.valid_languages:
            full_text = context_prefix_for_tokenization + lang
            full_token_ids = self.tokenizer.encode(full_text, add_special_tokens=False)

            context_end_idx = None
            if len(full_token_ids) >= len(context_token_ids):
                if full_token_ids[:len(context_token_ids)] == context_token_ids:
                    context_end_idx = len(context_token_ids)

            if context_end_idx is None:
                if self.debug:
                    logger.warning(f"Could not find context prefix in full tokenization of '{full_text}', skipping")
                continue

            lang_token_ids = full_token_ids[context_end_idx:]

            if not lang_token_ids:
                if self.debug:
                    logger.warning(f"No tokens extracted for language '{lang}', skipping")
                continue

            for i in range(len(lang_token_ids) + 1):
                token_prefix = tuple(lang_token_ids[:i])

                if token_prefix not in prefix_to_tokens:
                    prefix_to_tokens[token_prefix] = set()

                if i < len(lang_token_ids):
                    next_token_id = lang_token_ids[i]
                    prefix_to_tokens[token_prefix].add(next_token_id)
                else:
                    if self.newline_token:
                        prefix_to_tokens[token_prefix].add(self.newline_token)

        if self.debug:
            logger.debug(f"Built language prefix tree with {len(prefix_to_tokens)} token sequence prefixes")
            empty_prefix = tuple()
            if empty_prefix in prefix_to_tokens:
                first_tokens = prefix_to_tokens[empty_prefix]
                decoded_first = [(t, repr(self.tokenizer.decode([t]))) for t in sorted(first_tokens)]
                logger.debug(f"First tokens allowed for language (empty prefix): {decoded_first}")

        return prefix_to_tokens

    def diagnose_keyscale_prefix_tree(self):
        """
        Diagnose the keyscale prefix tree to help debug generation bias.
        Call this method to print detailed information about allowed tokens at each prefix.
        """
        print("=" * 60)
        print("KEYSCALE PREFIX TREE DIAGNOSIS")
        print("=" * 60)

        # Check empty prefix (first token)
        if "" in self.keyscale_prefix_tree:
            first_tokens = self.keyscale_prefix_tree[""]
            print(f"\n[Empty prefix] Allowed first tokens ({len(first_tokens)} total):")
            for t in sorted(first_tokens):
                decoded = self.tokenizer.decode([t])
                print(f"  Token {t}: {repr(decoded)}")
        else:
            print("\nWARNING: Empty prefix not in tree!")

        # Check some common prefixes
        test_prefixes = ["A", "B", "C", "D", "E", "F", "G"]
        for prefix in test_prefixes:
            # Try both with and without potential tokenizer artifacts
            for test_key in [prefix, prefix + " "]:
                if test_key in self.keyscale_prefix_tree:
                    tokens = self.keyscale_prefix_tree[test_key]
                    print(f"\n[Prefix {repr(test_key)}] Allowed tokens ({len(tokens)}):")
                    for t in sorted(tokens):
                        decoded = self.tokenizer.decode([t])
                        print(f"  Token {t}: {repr(decoded)}")

        # Show some complete keyscales that should be valid
        print(f"\n[Valid keyscales] Total: {len(self.valid_keyscales)}")
        sample = sorted(list(self.valid_keyscales))[:10]
        for ks in sample:
            print(f"  {repr(ks)}")

        print("=" * 60)
