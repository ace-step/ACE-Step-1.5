"""Gradio package: web UI composition for ACE-Step controls and outputs.

``create_gradio_interface`` is exposed lazily (PEP 562) so that importing
submodules that do not need gradio itself (e.g. the headless helpers used by
``acestep.api_server``) does not require the gradio package to be installed.
"""

__all__ = ["create_gradio_interface"]


def __getattr__(name):
    if name == "create_gradio_interface":
        from acestep.ui.gradio.interfaces import create_gradio_interface

        return create_gradio_interface
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals()) + __all__)
