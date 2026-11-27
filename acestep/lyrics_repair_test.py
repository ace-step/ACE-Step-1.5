"""Tests for the repairs of LM-written lyrics."""

import unittest

from acestep.lyrics_repair import is_french, repair_lm_lyrics


class RepairFrenchLostNTests(unittest.TestCase):
    def test_puts_back_the_n_seen_in_generations(self):
        self.assertEqual(
            repair_lm_lyrics("Mais pour l'étreinte, elle ferait\n'importe quoi\nJe l'ai vu", "fr"),
            "Mais pour l'étreinte, elle ferait n'importe quoi\nJe l'ai vu",
        )
        self.assertEqual(repair_lm_lyrics("Les étoiles brillent mais rien\n'est fini", "fr"),
                         "Les étoiles brillent mais rien n'est fini")

    def test_h_and_accented_vowels(self):
        self.assertEqual(repair_lm_lyrics("je\n'hésite plus", "fr"), "je n'hésite plus")
        self.assertEqual(repair_lm_lyrics("il\n'était pas là", "fr"), "il n'était pas là")

    def test_leaves_real_line_starts_alone(self):
        text = "[Verse 1]\n'est-ce\n\n'importe\nOui,\n'cause\nfin\n'Ton"
        # after a tag, after a blank line, after punctuation, before a consonant: no change
        self.assertEqual(repair_lm_lyrics(text, "fr"), text)

    def test_missing_n_before_a_vowel_is_not_guessed(self):
        self.assertEqual(repair_lm_lyrics("Les\néons qui brillent", "fr"), "Les\néons qui brillent")

    def test_only_french(self):
        text = "I want you\n'cause\nand\n'em all"
        self.assertEqual(repair_lm_lyrics(text, "en"), text)
        self.assertEqual(repair_lm_lyrics("rien\n'est", None), "rien\n'est")
        self.assertEqual(repair_lm_lyrics("rien\n'est", "FR"), "rien n'est")
        self.assertEqual(repair_lm_lyrics("", "fr"), "")

    def test_is_french(self):
        self.assertTrue(is_french("fr"))
        self.assertTrue(is_french(" fr-CA "))
        self.assertFalse(is_french("unknown"))
        self.assertFalse(is_french(None))


class CreateSampleRepairTests(unittest.TestCase):
    """The inspiration path (create_sample_from_query) returns repaired French lyrics."""

    def _handler(self, output_text):
        from acestep.llm_inference import LLMHandler

        handler = LLMHandler.__new__(LLMHandler)
        handler.llm_initialized = True
        handler.build_formatted_prompt_for_inspiration = lambda **_kwargs: "prompt"
        handler.generate_from_formatted_prompt = lambda **_kwargs: (output_text, "ok")
        return handler

    def test_french_inspiration_lyrics_are_repaired(self):
        output = "<think>\nbpm: 120\nlanguage: fr\n</think>\n\n[Verse 1]\nelle ferait\n'importe quoi\n"
        metadata, _ = self._handler(output).create_sample_from_query("q", vocal_language="fr")
        self.assertIn("elle ferait n'importe quoi", metadata["lyrics"])

    def test_other_language_untouched(self):
        output = "<think>\nbpm: 120\nlanguage: en\n</think>\n\n[Verse 1]\nI need you\n'cause\n"
        metadata, _ = self._handler(output).create_sample_from_query("q", vocal_language="en")
        self.assertIn("I need you\n'cause", metadata["lyrics"])


if __name__ == "__main__":
    unittest.main()
