import json
import os
from typing import List


def save_manifest(output_dir: str, metadata, output_paths: List[str]) -> str:
    """Save manifest.json listing all preprocessed samples."""
    manifest = {
        "metadata": metadata.to_dict(),
        "samples": output_paths,
        "num_samples": len(output_paths),
    }
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path
