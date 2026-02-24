"""Input normalization and batch preparation helpers for service generation."""

import random
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from acestep.constants import DEFAULT_DIT_INSTRUCTION

# Maximum batch size supported per coding guidelines
# (batch operations are supported up to 8 songs)
MAX_BATCH_SIZE = 8


class ServiceGenerateRequestMixin:
    """Prepare normalized service-generation inputs before diffusion execution."""

    def _build_service_seed_list(
        self,
        seed: Optional[Union[int, List[int]]],
        batch_size: int,
    ) -> Optional[List[int]]:
        """Normalize ``seed`` into a per-item list or ``None`` for random sampling."""
        if seed is None:
            return None
        if isinstance(seed, list):
            seed_list = list(seed)
            if len(seed_list) < batch_size:
                while len(seed_list) < batch_size:
                    seed_list.append(random.randint(0, 2**32 - 1))
            elif len(seed_list) > batch_size:
                seed_list = seed_list[:batch_size]
            return seed_list
        return [int(seed)] * batch_size

    def _normalize_service_generate_inputs(
        self,
        captions: Union[str, List[str]],
        lyrics: Union[str, List[str]],
        keys: Optional[Union[str, List[str]]],
        metas: Optional[Union[str, Dict[str, Any], List[Union[str, Dict[str, Any]]]]],
        vocal_languages: Optional[Union[str, List[str]]],
        repainting_start: Optional[Union[float, List[float]]],
        repainting_end: Optional[Union[float, List[float]]],
        instructions: Optional[Union[str, List[str]]],
        audio_code_hints: Optional[Union[str, List[str]]],
        infer_steps: int,
        seed: Optional[Union[int, List[int]]],
        return_intermediate: bool = False,
    ) -> Dict[str, Any]:
        """Normalize scalar/list generation inputs and clamp turbo infer steps."""
        if self.config.is_turbo and infer_steps > 8:
            logger.warning(
                "[service_generate] dmd_gan version: infer_steps {} exceeds maximum 8, clamping to 8",
                infer_steps,
            )
            infer_steps = 8

        # Convert captions to list and determine batch size
        if isinstance(captions, str):
            captions = [captions]
        
        batch_size = len(captions)
        
        # Validate and clamp batch size to maximum supported
        if batch_size > MAX_BATCH_SIZE:
            logger.warning(
                "[service_generate] Batch size {} exceeds maximum supported batch size ({}). "
                "Clamping to {}.",
                batch_size,
                MAX_BATCH_SIZE,
                MAX_BATCH_SIZE,
            )
            batch_size = MAX_BATCH_SIZE
            captions = captions[:batch_size]
        
        # Now convert other inputs to lists, using the clamped batch_size
        if isinstance(lyrics, str):
            lyrics = [lyrics]
        if isinstance(keys, str):
            keys = [keys]
        if isinstance(vocal_languages, str):
            vocal_languages = [vocal_languages]
        if isinstance(metas, (str, dict)):
            metas = [metas]
        if isinstance(repainting_start, (int, float)):
            repainting_start = [repainting_start]
        if isinstance(repainting_end, (int, float)):
            repainting_end = [repainting_end]
        
        # Truncate list inputs that exceed clamped batch size
        if keys is not None and len(keys) > batch_size:
            keys = keys[:batch_size]
        if metas is not None and len(metas) > batch_size:
            metas = metas[:batch_size]
        if vocal_languages is not None and len(vocal_languages) > batch_size:
            vocal_languages = vocal_languages[:batch_size]
        if repainting_start is not None and len(repainting_start) > batch_size:
            repainting_start = repainting_start[:batch_size]
        if repainting_end is not None and len(repainting_end) > batch_size:
            repainting_end = repainting_end[:batch_size]
        
        if len(lyrics) < batch_size:
            fill = lyrics[-1] if lyrics else ""
            lyrics = list(lyrics) + [fill] * (batch_size - len(lyrics))
        elif len(lyrics) > batch_size:
            lyrics = lyrics[:batch_size]

        if instructions is not None:
            instructions = self._normalize_instructions(
                instructions,
                batch_size,
                DEFAULT_DIT_INSTRUCTION,
            )
        if audio_code_hints is not None:
            audio_code_hints = self._normalize_audio_code_hints(audio_code_hints, batch_size)

        return {
            "captions": captions,
            "lyrics": lyrics,
            "keys": keys,
            "metas": metas,
            "vocal_languages": vocal_languages,
            "repainting_start": repainting_start,
            "repainting_end": repainting_end,
            "instructions": instructions,
            "audio_code_hints": audio_code_hints,
            "infer_steps": infer_steps,
            "seed_list": self._build_service_seed_list(seed=seed, batch_size=batch_size),
            "return_intermediate": return_intermediate,
        }
