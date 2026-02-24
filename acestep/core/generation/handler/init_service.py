"""Facade mixin that composes initialization helper modules."""

from .init_service_catalog import InitServiceCatalogMixin
from .init_service_downloads import InitServiceDownloadsMixin
from .init_service_loader import InitServiceLoaderMixin
from .init_service_memory_basic import InitServiceMemoryBasicMixin
from .init_service_memory_transfer import InitServiceMemoryTransferMixin
from .init_service_offload_context import InitServiceOffloadContextMixin
from .init_service_orchestrator import InitServiceOrchestratorMixin
from .init_service_setup import InitServiceSetupMixin


class InitServiceMixin(
    InitServiceCatalogMixin,
    InitServiceSetupMixin,
    InitServiceDownloadsMixin,
    InitServiceLoaderMixin,
    InitServiceOrchestratorMixin,
    InitServiceMemoryBasicMixin,
    InitServiceMemoryTransferMixin,
    InitServiceOffloadContextMixin,
):
    """Composed initialization mixin for AceStepHandler."""
