from .core import CoreMixin
from .dataframe import DataframeMixin
from .label_all import LabelAllMixin
from .label_single import LabelSingleMixin
from .metadata import MetadataMixin
from .preprocess import PreprocessMixin
from .scan import ScanMixin
from .serialization import SerializationMixin
from .update_sample import UpdateSampleMixin


class DatasetBuilder(
    CoreMixin,
    ScanMixin,
    LabelSingleMixin,
    LabelAllMixin,
    UpdateSampleMixin,
    MetadataMixin,
    SerializationMixin,
    DataframeMixin,
    PreprocessMixin,
):
    """Builder for creating training datasets from audio files."""

    pass
