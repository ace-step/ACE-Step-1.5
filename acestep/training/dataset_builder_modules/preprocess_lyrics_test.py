"""Tests that training encodes lyrics into the inference prompt shape.

Training previously tokenized bare lyrics while inference prepended
``# Languages\\n{lang}\\n\\n# Lyric\\n`` and appended ``<|endoftext|>``. Every
lyric token therefore sat at a different sequence position during training than
at generation, and no terminator was ever learned.
"""

import unittest
from unittest.mock import MagicMock

try:
    import torch

    from acestep.constants import LYRIC_GEN_PROMPT
    from acestep.core.generation.handler.prompt_utils import PromptMixin
    from acestep.training.dataset_builder_modules.preprocess_lyrics import (
        LYRIC_MAX_LENGTH,
        encode_lyrics,
    )

    _IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover
    torch = None
    LYRIC_GEN_PROMPT = None
    LYRIC_MAX_LENGTH = None
    PromptMixin = None
    encode_lyrics = None
    _IMPORT_ERROR = exc


def _fake_tokenizer(captured):
    """Build a tokenizer stub that records the text it was asked to encode."""

    def tokenize(text, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs
        return MagicMock(
            input_ids=torch.tensor([[1, 2, 3]]),
            attention_mask=torch.tensor([[1, 1, 1]]),
        )

    return tokenize


def _fake_encoder():
    """Build a text-encoder stub exposing a device and an embedding table."""
    encoder = MagicMock()
    encoder.parameters.return_value = iter([torch.zeros(1)])
    encoder.embed_tokens.return_value = torch.zeros(1, 3, 8)
    return encoder


@unittest.skipIf(encode_lyrics is None, f"import unavailable: {_IMPORT_ERROR}")
class LyricPromptParityTests(unittest.TestCase):
    """Training and inference must build one identical lyric prompt."""

    def test_training_prompt_matches_inference_prompt(self):
        """encode_lyrics tokenizes exactly what _format_lyrics produces."""
        captured = {}
        encode_lyrics(
            _fake_encoder(), _fake_tokenizer(captured), "Sohniye", "pa",
            torch.device("cpu"), torch.float32,
        )

        expected = PromptMixin._format_lyrics(None, "Sohniye", "pa")
        self.assertEqual(captured["text"], expected)

    def test_training_prompt_carries_header_and_terminator(self):
        """The encoded text has the language header and the lyric terminator."""
        captured = {}
        encode_lyrics(
            _fake_encoder(), _fake_tokenizer(captured), "Sohniye", "pa",
            torch.device("cpu"), torch.float32,
        )

        self.assertTrue(captured["text"].startswith("# Languages\npa\n\n# Lyric\n"))
        self.assertTrue(captured["text"].endswith("<|endoftext|>"))

    def test_training_truncation_matches_inference(self):
        """Lyrics are truncated at the inference budget, not the old 512."""
        captured = {}
        encode_lyrics(
            _fake_encoder(), _fake_tokenizer(captured), "la la", "hi",
            torch.device("cpu"), torch.float32,
        )

        self.assertEqual(LYRIC_MAX_LENGTH, 2048)
        self.assertEqual(captured["kwargs"]["max_length"], 2048)
        self.assertTrue(captured["kwargs"]["truncation"])

    def test_instrumental_lyrics_still_get_a_header(self):
        """Instrumental samples are formatted the same way, not special-cased."""
        captured = {}
        encode_lyrics(
            _fake_encoder(), _fake_tokenizer(captured), "[Instrumental]", "unknown",
            torch.device("cpu"), torch.float32,
        )

        self.assertEqual(
            captured["text"], "# Languages\nunknown\n\n# Lyric\n[Instrumental]<|endoftext|>"
        )


@unittest.skipIf(LYRIC_GEN_PROMPT is None, f"import unavailable: {_IMPORT_ERROR}")
class LyricTemplateContractTests(unittest.TestCase):
    """Pin the template's exact bytes.

    ``_extract_lyric_segment`` derives the start of the sung range from the
    header's token length and the end from ``<|endoftext|>``, so changing these
    bytes silently misaligns lyric timestamping and scoring.
    """

    def test_format_lyrics_output_is_unchanged(self):
        """Rendering matches the literal inference used before the refactor."""
        self.assertEqual(
            PromptMixin._format_lyrics(None, "line one", "pa"),
            "# Languages\npa\n\n# Lyric\nline one<|endoftext|>",
        )

    def test_alignment_header_is_a_prefix_of_the_template(self):
        """The offset header in lyric_alignment_common still matches."""
        alignment_header = f"# Languages\n{'pa'}\n\n# Lyric\n"
        self.assertTrue(LYRIC_GEN_PROMPT.format("pa", "x").startswith(alignment_header))

    def test_braces_in_lyrics_survive_formatting(self):
        """Lyrics are a format argument, so braces are not interpreted."""
        self.assertEqual(
            PromptMixin._format_lyrics(None, "oh {yeah} {0}", "pa"),
            "# Languages\npa\n\n# Lyric\noh {yeah} {0}<|endoftext|>",
        )


if __name__ == "__main__":
    unittest.main()
