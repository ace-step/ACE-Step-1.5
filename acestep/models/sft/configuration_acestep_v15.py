# Re-export from canonical location to avoid duplication.
# All model variants share the same AceStepConfig.
from acestep.models.common.configuration_acestep_v15 import AceStepConfig

__all__ = ["AceStepConfig"]
