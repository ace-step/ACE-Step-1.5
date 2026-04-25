"""
Constants for ACE-Step
Centralized constants used across the codebase
"""

# ==============================================================================
# Language Constants
# ==============================================================================

# Supported languages for vocal generation and language detection
# Covers major world languages with good TTS support in the underlying model
# 'unknown' is used when language cannot be determined automatically
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

# Musical note names using standard Western notation
KEYSCALE_NOTES = ['A', 'B', 'C', 'D', 'E', 'F', 'G']

# Supported accidentals: natural, ASCII sharp/flat, Unicode sharp/flat
KEYSCALE_ACCIDENTALS = ['', '#', 'b', '♯', '♭']  # empty + ASCII sharp/flat + Unicode sharp/flat

# Major and minor scale modes
KEYSCALE_MODES = ['major', 'minor']

# Generate all valid keyscales: 7 notes × 5 accidentals × 2 modes = 70 combinations
# Examples: "C major", "F# minor", "B♭ major"
VALID_KEYSCALES = set()
for note in KEYSCALE_NOTES:
    for acc in KEYSCALE_ACCIDENTALS:
        for mode in KEYSCALE_MODES:
            VALID_KEYSCALES.add(f"{note}{acc} {mode}")


# ==============================================================================
# Metadata Range Constants
# ==============================================================================

# BPM (Beats Per Minute) range - covers most musical styles
# 30 BPM: Very slow ballads, ambient music
# 300 BPM: Fast electronic dance music, extreme metal
BPM_MIN = 30
BPM_MAX = 300

# Duration range (in seconds) - balances quality vs. computational cost
# 10s: Short loops, musical excerpts
# 600s: Full songs, extended compositions (10 minutes)
DURATION_MIN = 10
DURATION_MAX = 600

# Valid time signatures - common musical meter patterns
# 2: 2/4 time (marches, polka)
# 3: 3/4 time (waltzes, ballads) 
# 4: 4/4 time (most pop, rock, hip-hop)
# 6: 6/8 time (compound time, folk dances)
VALID_TIME_SIGNATURES = [2, 3, 4, 6]


# ==============================================================================
# Task Type Constants  
# ==============================================================================

# All supported generation tasks across different model variants
TASK_TYPES = ["text2music", "repaint", "cover", "cover-nofsq", "extract", "lego", "complete"]

# Task types available for turbo models (optimized subset for speed)
# - text2music: Generate from text descriptions
# - repaint: Selective audio editing/regeneration  
# - cover: Style transfer using reference audio
TASK_TYPES_TURBO = ["text2music", "repaint", "cover", "cover-nofsq"]

# Task types available for base models (full feature set)
# Additional tasks requiring more computational resources:
# - extract: Separate individual tracks/stems from audio
# - lego: Multi-track generation (add layers)
# - complete: Automatic completion of partial audio
TASK_TYPES_BASE = ["text2music", "repaint", "cover", "cover-nofsq", "extract", "lego", "complete"]


# ==============================================================================
# Generation Mode Constants (UI-level modes that map to task types)
# ==============================================================================

# Default modes for turbo and SFT models (restricted set)
GENERATION_MODES_TURBO = ["Simple", "Custom", "Remix", "Repaint"]

# Extended modes for pure base models only — adds Extract/Lego/Complete
GENERATION_MODES_BASE = ["Simple", "Custom", "Remix", "Repaint", "Extract", "Lego", "Complete"]

# Mapping from generation mode to task_type value
MODE_TO_TASK_TYPE = {
    "Simple": "text2music",
    "Custom": "text2music",
    "Remix": "cover",
    "Repaint": "repaint",
    "Extract": "extract",
    "Lego": "lego",
    "Complete": "complete",
}


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
    "cover-nofsq": "Generate audio semantic tokens based on the given conditions:",
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

# Supported instrumental track types for multi-track generation and extraction
# Organized by instrument families for logical grouping:
# - Wind instruments: woodwinds, brass
# - Electronic: fx (effects), synth (synthesizer)  
# - String instruments: strings, guitar, bass
# - Rhythm section: percussion, drums, keyboard
# - Vocals: backing_vocals, vocals (lead vocals)
TRACK_NAMES = [
    "woodwinds", "brass", "fx", "synth", "strings", "percussion",
    "keyboard", "guitar", "bass", "drums", "backing_vocals", "vocals"
]

# Template for SFT (Supervised Fine-Tuning) model prompts
# Used to format inputs for the language model with instruction, caption, and metadata
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
