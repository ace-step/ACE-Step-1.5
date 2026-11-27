"""Tests for keeping the caption's singing language in line with the chosen language."""

import unittest

from acestep.caption_language import align_caption_language, language_name


class AlignCaptionLanguageTests(unittest.TestCase):
    def test_captions_seen_in_inspiration(self):
        seen = [
            ("A clear, emotive female lead vocal, sung in Portuguese, soars over the arrangement.",
             "A clear, emotive female lead vocal, sung in French, soars over the arrangement."),
            ("A clear, emotive female lead vocal, sung in Norwegian, soars", "A clear, emotive female lead vocal, sung in French, soars"),
            ("vocal, sung in Spanish, soars", "vocal, sung in French, soars"),
        ]
        for caption, expected in seen:
            self.assertEqual(align_caption_language(caption, "fr"), expected)

    def test_other_phrasings(self):
        self.assertEqual(align_caption_language("A Czech female vocal floats above.", "fr"), "A French female vocal floats above.")
        self.assertEqual(align_caption_language("Polish lyrics and a rap in the Haitian Creole language", "fr"),
                         "French lyrics and a rap in the French language")
        self.assertEqual(align_caption_language("lyrics delivered entirely in Mandarin", "fr"), "lyrics delivered entirely in French")
        self.assertEqual(align_caption_language("Portuguese-language vocals", "en"), "English-language vocals")

    def test_instruments_and_styles_are_left_alone(self):
        text = "Spanish guitar, a French horn, Latin percussion and a Brazilian groove, Japanese city pop."
        self.assertEqual(align_caption_language(text, "fr"), text)

    def test_same_language_or_no_choice_changes_nothing(self):
        text = "A female vocal, sung in Finnish."
        self.assertEqual(align_caption_language("A vocal sung in French.", "fr"), "A vocal sung in French.")
        self.assertEqual(align_caption_language(text, "unknown"), text)
        self.assertEqual(align_caption_language(text, None), text)
        self.assertEqual(align_caption_language(text, ""), text)
        self.assertEqual(align_caption_language("", "fr"), "")

    def test_language_name(self):
        self.assertEqual(language_name("fr"), "French")
        self.assertEqual(language_name(" PT-br "), "Portuguese")
        self.assertEqual(language_name("xx"), "")


class CreateSampleCaptionTests(unittest.TestCase):
    """The inspiration path returns a caption that names the chosen language."""

    def _handler(self, output_text):
        from acestep.llm_inference import LLMHandler

        handler = LLMHandler.__new__(LLMHandler)
        handler.llm_initialized = True
        handler.build_formatted_prompt_for_inspiration = lambda **_kwargs: "prompt"
        handler.generate_from_formatted_prompt = lambda **_kwargs: (output_text, "ok")
        return handler

    def test_inspiration_caption_follows_the_chosen_language(self):
        output = ("<think>\nbpm: 120\ncaption: A synth-pop track with a female vocal, sung in Czech, over pads.\n"
                  "language: fr\n</think>\n\n[Verse 1]\nla nuit\n")
        metadata, _ = self._handler(output).create_sample_from_query("q", vocal_language="fr")
        self.assertIn("sung in French", metadata["caption"])
        self.assertNotIn("Czech", metadata["caption"])

    def test_without_a_chosen_language_the_caption_is_kept(self):
        output = ("<think>\nbpm: 120\ncaption: A synth-pop track with a female vocal, sung in Czech, over pads.\n"
                  "</think>\n\n[Verse 1]\nla nuit\n")
        metadata, _ = self._handler(output).create_sample_from_query("q")
        self.assertIn("sung in Czech", metadata["caption"])


if __name__ == "__main__":
    unittest.main()
