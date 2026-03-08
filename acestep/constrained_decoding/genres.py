"""
Genre vocabulary handling mixin for constrained logits processing.

This module provides the GenresMixin class, which encapsulates all genre vocabulary
loading, trie construction, caption-based genre extraction, character-to-token
precomputation, and trie-based token filtering logic. It is designed to be used as
a mixin by MetadataConstrainedLogitsProcessor in the constrained logits processor
pipeline.
"""

import os
import re
from typing import Dict, List, Optional

from loguru import logger


class GenresMixin:
    """
    Mixin class providing genre vocabulary handling for MetadataConstrainedLogitsProcessor.

    This mixin manages:
      - Loading and hot-reloading a genres vocabulary file (one genre per line).
      - Building a trie (prefix tree) from the vocabulary for efficient prefix matching.
      - Extracting caption-relevant genres and building a smaller caption-specific trie.
      - Precomputing character-to-token mappings for O(1) lookup during generation.
      - Determining allowed tokens at each step based on trie state.

    No ``__init__`` is defined; all instance attributes are expected to be initialised
    by the host class (MetadataConstrainedLogitsProcessor).
    """

    def _load_genres_vocab(self):
        """
        Load genres vocabulary from file. Supports hot reload by checking file mtime.
        File format: one genre per line, lines starting with # are comments.
        """
        if not os.path.exists(self.genres_vocab_path):
            if self.debug:
                logger.debug(f"Genres vocab file not found: {self.genres_vocab_path}")
            return

        try:
            mtime = os.path.getmtime(self.genres_vocab_path)
            if mtime <= self.genres_vocab_mtime:
                return  # File hasn't changed

            with open(self.genres_vocab_path, 'r', encoding='utf-8') as f:
                genres = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        genres.append(line.lower())

                self.genres_vocab = genres
                self.genres_vocab_mtime = mtime
                self._build_genres_trie()

                if self.debug:
                    logger.debug(f"Loaded {len(self.genres_vocab)} genres from {self.genres_vocab_path}")
        except Exception as e:
            logger.warning(f"Failed to load genres vocab: {e}")

    def _build_genres_trie(self):
        """
        Build a trie (prefix tree) from genres vocabulary for efficient prefix matching.
        Each node is a dict with:
          - '_end': True if this node represents a complete genre
          - other keys: next characters in the trie
        """
        self.genres_trie = {}

        for genre in self.genres_vocab:
            node = self.genres_trie
            for char in genre:
                if char not in node:
                    node[char] = {}
                node = node[char]
            node['_end'] = True  # Mark end of a complete genre

        if self.debug:
            logger.debug(f"Built genres trie with {len(self.genres_vocab)} entries")

    def _extract_caption_genres(self, caption: str):
        """
        Extract genres from the user's caption that match entries in the vocabulary.
        This creates a smaller trie for faster and more relevant genre generation.

        Strategy (optimized - O(words * max_genre_len) instead of O(vocab_size)):
        1. Extract words/phrases from caption
        2. For each word, use trie to find all vocab entries that START with this word
        3. Build a separate trie from matched genres
        """
        if not caption or not self.genres_vocab:
            return

        caption_lower = caption.lower()
        matched_genres = set()

        # Extract words from caption (split by common delimiters)
        words = re.split(r'[,\s\-_/\\|]+', caption_lower)
        words = [w.strip() for w in words if w.strip() and len(w.strip()) >= 2]

        # For each word, find genres in trie that start with this word
        for word in words:
            # Find all genres starting with this word using trie traversal
            node = self._get_genres_trie_node(word)
            if node is not None:
                # Collect all complete genres under this node
                self._collect_complete_genres(node, word, matched_genres)

        # Also check if any word appears as a substring in short genres (< 20 chars)
        # This is a quick check for common single-word genres
        genres_set = set(self.genres_vocab)
        for word in words:
            if word in genres_set:
                matched_genres.add(word)

        if not matched_genres:
            if self.debug:
                logger.debug(f"No genres matched in caption, using full vocab")
            return

        # Build a trie from matched genres
        self.caption_matched_genres = list(matched_genres)
        self.caption_genres_trie = {}

        for genre in matched_genres:
            node = self.caption_genres_trie
            for char in genre:
                if char not in node:
                    node[char] = {}
                node = node[char]
            node['_end'] = True

        if self.debug:
            logger.debug(f"Matched {len(matched_genres)} genres from caption: {list(matched_genres)[:5]}...")

    def _collect_complete_genres(self, node: Dict, prefix: str, result: set, max_depth: int = 50):
        """
        Recursively collect all complete genres under a trie node.
        Limited depth to avoid too many matches.
        """
        if max_depth <= 0:
            return

        if node.get('_end', False):
            result.add(prefix)

        # Limit total collected genres to avoid slowdown
        if len(result) >= 100:
            return

        for char, child_node in node.items():
            if char not in ('_end', '_tokens'):
                self._collect_complete_genres(child_node, prefix + char, result, max_depth - 1)

    def _precompute_char_token_mapping(self):
        """
        Precompute mapping from characters to token IDs and token decoded texts.
        This allows O(1) lookup instead of calling tokenizer.encode()/decode() at runtime.

        Time complexity: O(vocab_size) - runs once during initialization

        Note: Many subword tokenizers (like Qwen) add space prefixes to tokens.
        We need to handle both the raw first char and the first non-space char.
        """
        self._char_to_tokens: Dict[str, set] = {}
        self._token_to_text: Dict[int, str] = {}  # Precomputed decoded text for each token

        # For each token in vocabulary, get its decoded text
        for token_id in range(self.vocab_size):
            try:
                text = self.tokenizer.decode([token_id])

                if not text:
                    continue

                # Store the decoded text (normalized to lowercase)
                # Keep leading spaces for proper concatenation (e.g., " rock" in "pop rock")
                # Only rstrip trailing whitespace, unless it's a pure whitespace token
                text_lower = text.lower()
                if text_lower.strip():  # Has non-whitespace content
                    normalized_text = text_lower.rstrip()
                else:  # Pure whitespace token
                    normalized_text = " "  # Normalize to single space
                self._token_to_text[token_id] = normalized_text

                # Map first character (including space) to this token
                first_char = text[0].lower()
                if first_char not in self._char_to_tokens:
                    self._char_to_tokens[first_char] = set()
                self._char_to_tokens[first_char].add(token_id)

                # Also map first non-space character to this token
                # This handles tokenizers that add space prefixes (e.g., " pop" -> maps to 'p')
                stripped_text = text.lstrip()
                if stripped_text and stripped_text != text:
                    first_nonspace_char = stripped_text[0].lower()
                    if first_nonspace_char not in self._char_to_tokens:
                        self._char_to_tokens[first_nonspace_char] = set()
                    self._char_to_tokens[first_nonspace_char].add(token_id)

            except Exception:
                continue

        if self.debug:
            logger.debug(f"Precomputed char->token mapping for {len(self._char_to_tokens)} unique characters")

    def _try_reload_genres_vocab(self):
        """Check if genres vocab file has been updated and reload if necessary."""
        if not os.path.exists(self.genres_vocab_path):
            return

        try:
            mtime = os.path.getmtime(self.genres_vocab_path)
            if mtime > self.genres_vocab_mtime:
                self._load_genres_vocab()
        except Exception:
            pass  # Ignore errors during hot reload check

    def _get_genres_trie_node(self, prefix: str) -> Optional[Dict]:
        """
        Get the trie node for a given prefix.
        Returns None if the prefix is not valid (no genres start with this prefix).
        """
        node = self.genres_trie
        for char in prefix.lower():
            if char not in node:
                return None
            node = node[char]
        return node

    def _is_complete_genre(self, text: str) -> bool:
        """Check if the given text is a complete genre in the vocabulary."""
        node = self._get_genres_trie_node(text.strip())
        return node is not None and node.get('_end', False)

    def _get_trie_node_from_trie(self, trie: Dict, prefix: str) -> Optional[Dict]:
        """Get a trie node from a specific trie (helper for caption vs full trie)."""
        node = trie
        for char in prefix.lower():
            if char not in node:
                return None
            node = node[char]
        return node

    def _get_allowed_genres_tokens(self) -> List[int]:
        """
        Get allowed tokens for genres field based on trie matching.

        The entire genres string (including commas) must match a complete entry in the vocab.
        For example, if vocab contains "pop, rock, jazz", the generated string must exactly
        match that entry - we don't treat commas as separators for individual genres.

        Strategy:
        1. If caption-matched genres exist, use that smaller trie first (faster + more relevant)
        2. If no caption matches or prefix not in caption trie, fallback to full vocab trie
        3. Get valid next characters from current trie node
        4. For each candidate token, verify the full decoded text forms a valid trie prefix
        """
        if not self.genres_vocab:
            # No vocab loaded, allow all except newline if empty
            return []

        # Use the full accumulated value (don't split by comma - treat as single entry)
        accumulated = self.accumulated_value.lower()
        current_genre_prefix = accumulated.strip()

        # Determine which trie to use: caption-matched (priority) or full vocab (fallback)
        use_caption_trie = False
        current_node = None

        # Try caption-matched trie first if available
        if self.caption_genres_trie:
            if current_genre_prefix == "":
                current_node = self.caption_genres_trie
                use_caption_trie = True
            else:
                current_node = self._get_trie_node_from_trie(self.caption_genres_trie, current_genre_prefix)
                if current_node is not None:
                    use_caption_trie = True

        # Fallback to full vocab trie
        if current_node is None:
            if current_genre_prefix == "":
                current_node = self.genres_trie
            else:
                current_node = self._get_genres_trie_node(current_genre_prefix)

        if current_node is None:
            # Invalid prefix, force newline to end
            if self.newline_token:
                return [self.newline_token]
            return []

        # Get valid next characters from trie node
        valid_next_chars = set(k for k in current_node.keys() if k not in ('_end', '_tokens'))

        # If current value is a complete genre, allow newline to end
        is_complete = current_node.get('_end', False)

        if not valid_next_chars:
            # No more characters to match, only allow newline if complete
            allowed = set()
            if is_complete and self.newline_token:
                allowed.add(self.newline_token)
            return list(allowed)

        # Collect candidate tokens based on first character
        candidate_tokens = set()
        for char in valid_next_chars:
            if char in self._char_to_tokens:
                candidate_tokens.update(self._char_to_tokens[char])

        # Select the appropriate trie for validation
        active_trie = self.caption_genres_trie if use_caption_trie else self.genres_trie

        # Validate each candidate token: check if prefix + decoded_token is a valid trie prefix
        allowed = set()
        for token_id in candidate_tokens:
            # Use precomputed decoded text (already normalized)
            decoded_normalized = self._token_to_text.get(token_id, "")

            if not decoded_normalized or not decoded_normalized.strip():
                # Token decodes to empty or only whitespace - allow if space/comma is a valid next char
                if ' ' in valid_next_chars or ',' in valid_next_chars:
                    allowed.add(token_id)
                continue

            # Build new prefix by appending decoded token
            # Handle space-prefixed tokens (e.g., " rock" from "pop rock")
            if decoded_normalized.startswith(' ') or decoded_normalized.startswith(','):
                # Token has leading space/comma - append directly
                new_prefix = current_genre_prefix + decoded_normalized
            else:
                new_prefix = current_genre_prefix + decoded_normalized

            # Check if new_prefix is a valid prefix in the active trie
            new_node = self._get_trie_node_from_trie(active_trie, new_prefix)
            if new_node is not None:
                allowed.add(token_id)

        # If current value is a complete genre, also allow newline
        if is_complete and self.newline_token:
            allowed.add(self.newline_token)

        return list(allowed)
