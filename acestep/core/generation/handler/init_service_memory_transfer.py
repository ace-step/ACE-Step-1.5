"""Recursive model/tensor transfer helpers for offload workflows."""

import torch
from loguru import logger


class InitServiceMemoryTransferMixin:
    """Helpers that move modules/parameters across devices and dtypes."""

    def _move_module_recursive(self, module, target_device, dtype=None, visited=None):
        """Recursively move a module and all submodules to the target device.

        Uses in-place ``param.data`` replacement instead of creating new
        ``nn.Parameter`` wrappers, reducing transient memory allocations.
        """
        if visited is None:
            visited = set()

        module_id = id(module)
        if module_id in visited:
            return
        visited.add(module_id)

        for param_name, param in module._parameters.items():
            if param is None:
                continue
            if self._is_on_target_device(param, target_device):
                if dtype is not None and param.is_floating_point() and param.dtype != dtype:
                    param.data = param.data.to(dtype)
                continue
            if self._is_quantized_tensor(param):
                module._parameters[param_name] = self._move_quantized_param(param, target_device)
            else:
                new_data = param.data.to(target_device)
                if dtype is not None and new_data.is_floating_point():
                    new_data = new_data.to(dtype)
                param.data = new_data

        for buf_name, buf in module._buffers.items():
            if buf is not None and not self._is_on_target_device(buf, target_device):
                module._buffers[buf_name] = buf.to(target_device)

        # Note: only traverses registered submodules (_modules).  Modules stored
        # as plain object attributes (not via add_module / __setattr__) will not
        # be visited.  Standard PyTorch modules register children automatically.
        for _, child in module._modules.items():
            if child is not None:
                self._move_module_recursive(child, target_device, dtype, visited)

    def _move_quantized_param(self, param, target_device):
        """Move an AffineQuantizedTensor to target device using ``_apply_fn_to_data`` when available."""
        if hasattr(param, "_apply_fn_to_data"):
            return torch.nn.Parameter(
                param._apply_fn_to_data(lambda x: x.to(target_device)),
                requires_grad=param.requires_grad,
            )
        moved = param.to(target_device)
        return torch.nn.Parameter(moved, requires_grad=param.requires_grad)

    def _recursive_to_device(self, model, device, dtype=None):
        """Recursively move parameters and buffers to the specified device.

        Tries the fast ``model.to()`` path first.  Only falls back to
        manual recursive transfer when the fast path raises
        ``NotImplementedError`` (e.g. for torchao quantized tensors).
        """
        target_device = torch.device(device) if isinstance(device, str) else device

        fast_path_ok = True
        try:
            if dtype is not None:
                model.to(device=target_device, dtype=dtype)
            else:
                model.to(target_device)
        except NotImplementedError:
            fast_path_ok = False
            logger.info(
                "[_recursive_to_device] model.to() raised NotImplementedError "
                "(AffineQuantizedTensor on older torch). Moving parameters individually."
            )
            self._move_module_recursive(model, target_device, dtype)

        # Only do the follow-up recursive sweep when the fast path succeeded
        # but left some parameters on the wrong device (rare edge case with
        # custom module __setattr__ or quantized submodules).
        if fast_path_ok and device != "cpu":
            wrong_device_params = []
            for name, param in model.named_parameters():
                if not self._is_on_target_device(param, device):
                    wrong_device_params.append(name)

            if wrong_device_params:
                logger.warning(
                    f"[_recursive_to_device] {len(wrong_device_params)} parameters on wrong device "
                    f"after model.to(), retrying with recursive move"
                )
                self._move_module_recursive(model, target_device, dtype)

        if device != "cpu":
            self._synchronize()

            still_wrong = []
            for name, param in model.named_parameters():
                if not self._is_on_target_device(param, device):
                    still_wrong.append(f"{name} on {param.device}")
            if still_wrong:
                logger.error(
                    f"[_recursive_to_device] CRITICAL: {len(still_wrong)} parameters still on wrong device: {still_wrong[:10]}"
                )
