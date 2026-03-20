"""Thread safety tests for the i18n singleton and ContextVar isolation."""

import contextvars
import sys
import threading
import unittest
from unittest.mock import patch

from acestep.ui.gradio.i18n.i18n import (
    _current_language_var,
    _i18n_lock,
    get_i18n,
    reset_language_context,
    set_language_context,
    t,
)


class I18nThreadSafetyTests(unittest.TestCase):
    """Verify get_i18n() returns a single instance under concurrent access."""

    def test_concurrent_get_i18n_returns_same_instance(self):
        """Multiple threads calling get_i18n() must all receive the same object."""
        results: list[int] = []
        errors: list[str] = []
        barrier = threading.Barrier(8)

        def _call_get_i18n() -> None:
            """Fetch singleton after barrier synchronization."""
            try:
                barrier.wait(timeout=5)
                results.append(id(get_i18n()))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"get_i18n failed: {exc!r}")

        threads = [threading.Thread(target=_call_get_i18n) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        self.assertEqual(errors, [], f"Thread failure detected: {errors}")
        self.assertEqual(
            len(set(results)), 1,
            "get_i18n() returned different instances across threads",
        )

    def test_lock_attribute_exists(self):
        """Module-level lock must be present."""
        self.assertIsInstance(_i18n_lock, type(threading.Lock()))


class ContextVarIsolationTests(unittest.TestCase):
    """Verify per-request language isolation via ContextVar."""

    def setUp(self):
        """Ensure ContextVar is clean before each test."""
        # Reset to default (None) so tests don't leak state
        tok = _current_language_var.set(None)
        self.addCleanup(_current_language_var.reset, tok)

    def test_contextvar_overrides_instance_language(self):
        """t() must return the ContextVar language's translation, not the instance default."""
        i18n = get_i18n()
        i18n.set_language("en")
        en_title = t("app.title")

        token = set_language_context("zh")
        try:
            zh_title = t("app.title")
            # The ContextVar must have changed the language t() uses
            self.assertEqual(_current_language_var.get(), "zh")
            self.assertNotEqual(
                en_title, zh_title,
                "t() returned the same string for en and zh — ContextVar was ignored",
            )
        finally:
            reset_language_context(token)

        # After reset, t() falls back to the instance default (en)
        self.assertIsNone(_current_language_var.get())
        self.assertEqual(t("app.title"), en_title)

    def test_contextvar_none_falls_back_to_instance(self):
        """When ContextVar is unset (None), t() should use instance default."""
        i18n = get_i18n()
        i18n.set_language("en")

        self.assertIsNone(_current_language_var.get())
        # t() should still work — it falls back to instance language
        result = t("nonexistent.key.for.test")
        self.assertEqual(result, "nonexistent.key.for.test")

    def test_reset_restores_previous_value(self):
        """reset_language_context must restore the prior ContextVar value."""
        token1 = set_language_context("ja")
        try:
            self.assertEqual(_current_language_var.get(), "ja")
            token2 = set_language_context("zh")
            try:
                self.assertEqual(_current_language_var.get(), "zh")
            finally:
                reset_language_context(token2)
            # Should be back to "ja"
            self.assertEqual(_current_language_var.get(), "ja")
        finally:
            reset_language_context(token1)
        self.assertIsNone(_current_language_var.get())

    def test_concurrent_contexts_are_isolated(self):
        """Two threads with different ContextVar values must not interfere."""
        barrier = threading.Barrier(2)
        results: dict[str, str | None] = {}
        errors: list[str] = []

        def _worker(name: str, lang: str) -> None:
            """Set ContextVar, wait for peer, then verify own value."""
            try:
                token = set_language_context(lang)
                try:
                    # Both threads set their ContextVar, then sync
                    barrier.wait(timeout=5)
                    # Each thread should still see its own language
                    results[name] = _current_language_var.get()
                finally:
                    reset_language_context(token)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name} failed: {exc!r}")

        t1 = threading.Thread(target=_worker, args=("thread_zh", "zh"))
        t2 = threading.Thread(target=_worker, args=("thread_ja", "ja"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Thread failure: {errors}")
        self.assertEqual(results["thread_zh"], "zh",
                         "Thread with zh context saw wrong language")
        self.assertEqual(results["thread_ja"], "ja",
                         "Thread with ja context saw wrong language")

    def test_mixed_contextvar_and_fallback_threads(self):
        """One thread with ContextVar override, one without, must not interfere."""
        i18n = get_i18n()
        i18n.set_language("en")
        en_title = t("app.title")

        barrier = threading.Barrier(2)
        results: dict[str, str] = {}
        errors: list[str] = []

        def _worker_with_context() -> None:
            """Set ContextVar to zh and translate."""
            try:
                token = set_language_context("zh")
                try:
                    barrier.wait(timeout=5)
                    results["with_ctx"] = t("app.title")
                finally:
                    reset_language_context(token)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"with_context failed: {exc!r}")

        def _worker_without_context() -> None:
            """No ContextVar — should use instance default (en)."""
            try:
                barrier.wait(timeout=5)
                results["without_ctx"] = t("app.title")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"without_context failed: {exc!r}")

        t1 = threading.Thread(target=_worker_with_context)
        t2 = threading.Thread(target=_worker_without_context)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Thread failure: {errors}")
        # Thread without ContextVar must see the instance default (en)
        self.assertEqual(results["without_ctx"], en_title,
                         "Fallback thread got wrong language")
        # Thread with ContextVar must see zh (different from en)
        self.assertNotEqual(results["with_ctx"], en_title,
                            "ContextVar thread got instance default instead of zh")

    def test_set_language_context_warns_on_invalid_language(self):
        """set_language_context logs a warning when the language is not in translations."""
        # Ensure singleton exists so validation can run
        get_i18n()
        # "xyz_invalid" is not a loaded translation
        with patch.object(
            sys.modules[set_language_context.__module__], "logger",
        ) as mock_logger:
            token = set_language_context("xyz_invalid")
            try:
                # ContextVar is still set (graceful degradation)
                self.assertEqual(_current_language_var.get(), "xyz_invalid")
                # Warning must have fired exactly once
                mock_logger.warning.assert_called_once()
                # t() should fall back to English, then to key itself
                result = t("app.title")
                # Should get the English fallback, not the raw key
                self.assertNotEqual(result, "app.title",
                                    "Expected English fallback, got raw key")
            finally:
                reset_language_context(token)

    def test_contextvar_isolation_in_copy_context(self):
        """contextvars.copy_context isolates changes from the parent."""
        parent_token = set_language_context("en")
        try:
            parent_val = _current_language_var.get()

            def _child() -> str:
                """Run in a copied context; change should not leak back."""
                set_language_context("zh")
                return _current_language_var.get()

            ctx = contextvars.copy_context()
            child_val = ctx.run(_child)

            self.assertEqual(parent_val, "en")
            self.assertEqual(child_val, "zh")
            # Parent context is unchanged
            self.assertEqual(_current_language_var.get(), "en")
        finally:
            reset_language_context(parent_token)


if __name__ == "__main__":
    unittest.main()
