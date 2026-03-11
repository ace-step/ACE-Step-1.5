"""Unit tests for release-task request model defaults and compatibility flags."""

import unittest

from acestep.api.http.release_task_models import GenerateMusicRequest
from acestep.constants import DEFAULT_DIT_INSTRUCTION


class ReleaseTaskModelsTests(unittest.TestCase):
    """Behavior tests for release-task request model schema defaults."""

    def test_generate_music_request_preserves_legacy_defaults(self):
        """Model should expose same default values used by existing clients."""

        req = GenerateMusicRequest()
        self.assertEqual("", req.prompt)
        self.assertEqual("text2music", req.task_type)
        self.assertEqual("mp3", req.audio_format)
        self.assertEqual(DEFAULT_DIT_INSTRUCTION, req.instruction)
        self.assertTrue(req.use_random_seed)

    def test_new_fields_have_expected_defaults(self):
        """New audio_code_string and cover_noise_strength should default to safe values."""

        req = GenerateMusicRequest()
        self.assertEqual("", req.audio_code_string)
        self.assertAlmostEqual(0.0, req.cover_noise_strength)

    def test_audio_code_string_and_cover_noise_strength_are_accepted(self):
        """Model should accept user-supplied audio_code_string and cover_noise_strength."""

        req = GenerateMusicRequest(audio_code_string="<|audio_code_1|>", cover_noise_strength=0.75)
        self.assertEqual("<|audio_code_1|>", req.audio_code_string)
        self.assertAlmostEqual(0.75, req.cover_noise_strength)


if __name__ == "__main__":
    unittest.main()
