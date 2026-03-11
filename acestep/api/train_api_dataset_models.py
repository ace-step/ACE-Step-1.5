"""Request payload schemas and sample serialization for training dataset routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, root_validator


class ScanDirectoryRequest(BaseModel):
    """Request payload for scanning a directory into a dataset."""

    audio_dir: str = Field(..., description="Directory path to scan for audio files")
    dataset_name: str = Field(default="my_lora_dataset", description="Dataset name")
    custom_tag: str = Field(default="", description="Custom activation tag")
    tag_position: str = Field(default="replace", description="Tag position: prepend/append/replace")
    all_instrumental: bool = Field(default=True, description="All tracks instrumental")


class LoadDatasetRequest(BaseModel):
    """Request payload for loading an existing dataset JSON file."""

    dataset_path: str = Field(..., description="Path to dataset JSON file")


class AutoLabelRequest(BaseModel):
    """Request payload for auto-labeling dataset samples."""

    skip_metas: bool = Field(default=False, description="Skip BPM/Key/TimeSig generation")
    format_lyrics: bool = Field(default=False, description="Format user lyrics via LLM")
    transcribe_lyrics: bool = Field(default=False, description="Transcribe lyrics from audio")
    only_unlabeled: bool = Field(default=False, description="Only label unlabeled samples")

    lm_model_path: Optional[str] = Field(
        default=None,
        description="Optional LM model path to use for labeling (temporary switch)",
    )

    save_path: Optional[str] = Field(
        default=None,
        description="Optional dataset JSON path to persist progress during auto-label",
    )

    chunk_size: int = Field(default=16, ge=1, description="Chunk size for batch audio encoding")
    batch_size: int = Field(default=1, ge=1, description="Batch size for batch audio encoding")

    @root_validator(pre=True)
    def _backward_compatible_field_names(cls, values: Dict[str, Any]):
        """Map legacy payload fields to current request field names."""

        if values is None:
            return values

        if "chunk_size" not in values or values.get("chunk_size") is None:
            for key in ("hunk_size", "hunksize"):
                if key in values and values.get(key) is not None:
                    values["chunk_size"] = values[key]
                    break

        if "batch_size" not in values or values.get("batch_size") is None:
            for key in ("batchsize",):
                if key in values and values.get(key) is not None:
                    values["batch_size"] = values[key]
                    break

        return values


class SaveDatasetRequest(BaseModel):
    """Request payload for persisting current dataset state."""

    save_path: str = Field(..., description="Path to save dataset JSON")
    dataset_name: str = Field(default="my_lora_dataset", description="Dataset name")
    custom_tag: Optional[str] = Field(default=None, description="Custom activation tag")
    tag_position: Optional[str] = Field(default=None, description="Tag position: prepend/append/replace")
    all_instrumental: Optional[bool] = Field(default=None, description="All tracks instrumental")
    genre_ratio: Optional[int] = Field(default=None, ge=0, le=100, description="Genre vs caption ratio")


class UpdateSampleRequest(BaseModel):
    """Request payload for updating a single dataset sample."""

    sample_idx: int = Field(..., ge=0, description="Sample index")
    caption: str = Field(default="", description="Music description")
    genre: str = Field(default="", description="Genre tags")
    prompt_override: Optional[str] = Field(default=None, description="caption/genre/None")
    lyrics: str = Field(default="[Instrumental]", description="Lyrics")
    bpm: Optional[int] = Field(default=None, description="BPM")
    keyscale: str = Field(default="", description="Musical key")
    timesignature: str = Field(default="", description="Time signature")
    language: str = Field(default="unknown", description="Vocal language")
    is_instrumental: bool = Field(default=True, description="Instrumental track")


class PreprocessDatasetRequest(BaseModel):
    """Request payload for dataset tensor preprocessing."""

    output_dir: str = Field(..., description="Output directory for preprocessed tensors")
    skip_existing: bool = Field(default=False, description="Skip tensors that already exist (by sample id filename)")


def _serialize_samples(builder: Any) -> list[Dict[str, Any]]:
    """Return stable sample payload list for dataset endpoints."""

    return [
        {
            "index": i,
            "filename": sample.filename,
            "audio_path": sample.audio_path,
            "duration": sample.duration,
            "caption": sample.caption,
            "genre": sample.genre,
            "prompt_override": sample.prompt_override,
            "lyrics": sample.lyrics,
            "bpm": sample.bpm,
            "keyscale": sample.keyscale,
            "timesignature": sample.timesignature,
            "language": sample.language,
            "is_instrumental": sample.is_instrumental,
            "labeled": sample.labeled,
        }
        for i, sample in enumerate(builder.samples)
    ]
