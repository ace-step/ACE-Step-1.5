"""
Constants for ACE-Step
Centralized constants used across the codebase
"""

# ==============================================================================
# Language Constants
# ==============================================================================

VALID_LANGUAGES = [
    'ar', 'az', 'bg', 'bn', 'ca', 'cs', 'da', 'de', 'el', 'en',
    'es', 'fa', 'fi', 'fr', 'he', 'hi', 'hr', 'ht', 'hu', 'id',
    'is', 'it', 'ja', 'ko', 'la', 'lt', 'ms', 'ne', 'nl', 'no',
    'pa', 'pl', 'pt', 'ro', 'ru', 'sa', 'sk', 'sr', 'sv', 'sw',
    'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi', 'yue', 'zh',
    'unknown'
]


# ==============================================================================
# Keyscale Constants
# ==============================================================================

KEYSCALE_NOTES = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
KEYSCALE_ACCIDENTALS = ['', '#', 'b', '♯', '♭']  # empty + ASCII sharp/flat + Unicode sharp/flat
KEYSCALE_MODES = ['major', 'minor']

# Generate all valid keyscales: 7 notes × 5 accidentals × 2 modes = 70 combinations
VALID_KEYSCALES = set()
for note in KEYSCALE_NOTES:
    for acc in KEYSCALE_ACCIDENTALS:
        for mode in KEYSCALE_MODES:
            VALID_KEYSCALES.add(f"{note}{acc} {mode}")


# ==============================================================================
# Metadata Range Constants
# ==============================================================================

# BPM (Beats Per Minute) range
BPM_MIN = 30
BPM_MAX = 300

# Duration range (in seconds)
DURATION_MIN = 10
DURATION_MAX = 600

# Valid time signatures
VALID_TIME_SIGNATURES = [2, 3, 4, 6]


# ==============================================================================
# Task Type Constants
# ==============================================================================

TASK_TYPES = ["text2music", "repaint", "cover", "extract", "lego", "complete"]

# Task types available for turbo models (subset)
TASK_TYPES_TURBO = ["text2music", "repaint", "cover"]

# Task types available for base models (full set)
TASK_TYPES_BASE = ["text2music", "repaint", "cover", "extract", "lego", "complete"]


# ==============================================================================
# Instruction Constants
# ==============================================================================

# Default instructions
DEFAULT_DIT_INSTRUCTION = "Fill the audio semantic mask based on the given conditions:"
DEFAULT_LM_INSTRUCTION = "Generate audio semantic tokens based on the given conditions:"
DEFAULT_LM_UNDERSTAND_INSTRUCTION = "Understand the given musical conditions and describe the audio semantics accordingly:"
DEFAULT_LM_INSPIRED_INSTRUCTION = "Expand the user's input into a more detailed and specific musical description:"
DEFAULT_LM_REWRITE_INSTRUCTION = "Format the user's input into a more detailed and specific musical description:"

# Instruction templates for each task type
# Note: Some instructions use placeholders like {TRACK_NAME} or {TRACK_CLASSES}
# These should be formatted using .format() or f-strings when used
TASK_INSTRUCTIONS = {
    "text2music": "Fill the audio semantic mask based on the given conditions:",
    "repaint": "Repaint the mask area based on the given conditions:",
    "cover": "Generate audio semantic tokens based on the given conditions:",
    "extract": "Extract the {TRACK_NAME} track from the audio:",
    "extract_default": "Extract the track from the audio:",
    "lego": "Generate the {TRACK_NAME} track based on the audio context:",
    "lego_default": "Generate the track based on the audio context:",
    "complete": "Complete the input track with {TRACK_CLASSES}:",
    "complete_default": "Complete the input track:",
}


# ==============================================================================
# Track/Instrument Constants
# ==============================================================================

TRACK_NAMES = [
    "woodwinds", "brass", "fx", "synth", "strings", "percussion",
    "keyboard", "guitar", "bass", "drums", "backing_vocals", "vocals"
]

SFT_GEN_PROMPT = """# Instruction
{}

# Caption
{}

# Metas
{}<|endoftext|>
"""


# ==============================================================================
# GPU Memory Configuration Constants
# ==============================================================================

# GPU tier thresholds (in GB)
GPU_TIER_THRESHOLDS = {
    "tier1": 4,    # <= 4GB
    "tier2": 6,    # 4-6GB
    "tier3": 8,    # 6-8GB
    "tier4": 12,   # 8-12GB
    "tier5": 16,   # 12-16GB
    "tier6": 24,   # 16-24GB
    # "unlimited" for >= 24GB
}

# LM model memory requirements (in GB)
LM_MODEL_MEMORY_GB = {
    "0.6B": 3.0,
    "1.7B": 8.0,
    "4B": 12.0,
}

# LM model names mapping
LM_MODEL_NAMES = {
    "0.6B": "acestep-5Hz-lm-0.6B",
    "1.7B": "acestep-5Hz-lm-1.7B",
    "4B": "acestep-5Hz-lm-4B",
}


# ==============================================================================
# Debug Constants
# ==============================================================================

# Tensor debug mode (values: "OFF" | "ON" | "VERBOSE")
TENSOR_DEBUG_MODE = "OFF"

# Placeholder debug switches for other main functionality (default "OFF")
# Update names/usage as features adopt them.
DEBUG_API_SERVER = "OFF"
DEBUG_INFERENCE = "OFF"
DEBUG_TRAINING = "OFF"
DEBUG_DATASET = "OFF"
DEBUG_AUDIO = "OFF"
DEBUG_LLM = "OFF"
DEBUG_UI = "OFF"
DEBUG_MODEL_LOADING = "OFF"
DEBUG_GPU = "OFF"
