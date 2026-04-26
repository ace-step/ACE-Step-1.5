import os
from glob import glob
import torch
from torch import nn
from safetensors import safe_open


def default_weight_loader(param: nn.Parameter, loaded_weight: torch.Tensor):
    param.data.copy_(loaded_weight)


def _get_parameter_safe(model: nn.Module, weight_name: str):
    """
    Try to get parameter from model, handling name mismatches.

    Some models have nested structure (e.g., Qwen3ForCausalLM has model.embed_tokens)
    but weight files may have flat names (embed_tokens.weight).
    """
    # Try direct access first
    try:
        return model.get_parameter(weight_name)
    except AttributeError:
        pass

    # Try with 'model.' prefix (for nested model structure)
    try:
        prefixed_name = f"model.{weight_name}"
        return model.get_parameter(prefixed_name)
    except AttributeError:
        pass

    # Try removing 'model.' prefix
    if weight_name.startswith("model."):
        try:
            unprefixed_name = weight_name[6:]  # Remove 'model.' prefix
            return model.get_parameter(unprefixed_name)
        except AttributeError:
            pass

    return None


def load_model(model: nn.Module, path: str):
    packed_modules_mapping = getattr(model, "packed_modules_mapping", {})
    safetensor_files = glob(os.path.join(path, "*.safetensors"))

    if not safetensor_files:
        raise FileNotFoundError(f"No .safetensors files found in {path}")

    for file in safetensor_files:
        with safe_open(file, "pt", "cpu") as f:
            for weight_name in f.keys():
                for k in packed_modules_mapping:
                    if k in weight_name:
                        v, shard_id = packed_modules_mapping[k]
                        param_name = weight_name.replace(k, v)
                        param = _get_parameter_safe(model, param_name)
                        if param is None:
                            print(f"[loader] Warning: Parameter not found: {param_name}")
                            continue
                        weight_loader = getattr(param, "weight_loader")
                        weight_loader(param, f.get_tensor(weight_name), shard_id)
                        break
                else:
                    param = _get_parameter_safe(model, weight_name)
                    if param is None:
                        print(f"[loader] Warning: Parameter not found: {weight_name}")
                        continue
                    weight_loader = getattr(param, "weight_loader", default_weight_loader)
                    weight_loader(param, f.get_tensor(weight_name))
