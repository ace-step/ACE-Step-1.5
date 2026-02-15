import torch
import torch.nn as nn
import torch.nn.functional as F

from transformers.models.qwen3.modeling_qwen3 import Qwen3MLP


class MusaFusedQwen3MLP(nn.Module):
    """
    MLP layer optimized using torch_musa fusion operator.
    """
    def __init__(self, original_mlp: Qwen3MLP):
        super().__init__()
        self.hidden_size = original_mlp.hidden_size
        self.intermediate_size = original_mlp.intermediate_size
        
        self.fused_proj = nn.Linear(
            self.hidden_size, 
            2 * self.intermediate_size, 
            bias=False
        )
        
        with torch.no_grad():
            fused_weight = torch.cat([
                original_mlp.gate_proj.weight, 
                original_mlp.up_proj.weight
            ], dim=0)
            self.fused_proj.weight.copy_(fused_weight)
            
            self.down_proj = original_mlp.down_proj

    def forward(self, x):
        return self.down_proj(F.swish_glu(self.fused_proj(x)))

def apply_fused_musa_mlp(model):
    replaced_count = 0
    
    for name, module in model.named_modules():
        if isinstance(module, Qwen3MLP):
            parent_name = name.rsplit('.', 1)[0]
            child_name = name.rsplit('.', 1)[1]
            
            parent_module = model.get_submodule(parent_name)
            
            fused_mlp = MusaFusedQwen3MLP(module)
            fused_mlp.to(device=module.down_proj.weight.device, dtype=module.down_proj.weight.dtype)
            
            setattr(parent_module, child_name, fused_mlp)
            replaced_count += 1
            
    print(f"A total of {replaced_count} Qwen3MLP modules were replaced.")
    return model
