"""Recursive model/tensor transfer helpers for offload workflows."""

import torch
from loguru import logger


class InitServiceMemoryTransferMixin:
    """Helpers that move modules/parameters across devices and dtypes."""

    def _move_module_recursive(self, module, target_device, dtype=None, visited=None):
        """Recursively move a module and all submodules to the target device."""
        if visited is None:
            visited = set()

        module_id = id(module)
        if module_id in visited:
            return
        visited.add(module_id)

        module.to(target_device)
        if dtype is not None:
            module.to(dtype)

        for param_name, param in module._parameters.items():
            if param is not None and not self._is_on_target_device(param, target_device):
                if self._is_quantized_tensor(param):
                    moved_param = self._move_quantized_param(param, target_device)
                else:
                    moved_param = torch.nn.Parameter(
                        param.data.to(target_device), requires_grad=param.requires_grad
                    )
                if dtype is not None and moved_param.is_floating_point():
                    moved_param = torch.nn.Parameter(
                        moved_param.data.to(dtype), requires_grad=param.requires_grad
                    )
                module._parameters[param_name] = moved_param

        for buf_name, buf in module._buffers.items():
            if buf is not None and not self._is_on_target_device(buf, target_device):
                module._buffers[buf_name] = buf.to(target_device)

        for _, child in module._modules.items():
            if child is not None:
                self._move_module_recursive(child, target_device, dtype, visited)

        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(module, attr_name, None)
                if isinstance(attr, torch.nn.Module) and id(attr) not in visited:
                    self._move_module_recursive(attr, target_device, dtype, visited)
            except (AttributeError, TypeError) as exc:
                log = getattr(self, "logger", logger)
                log.warning(
                    f"[_move_module_recursive] Skipping attr '{attr_name}' during recursive move: {exc}"
                )

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
        """Recursively move parameters and buffers to the specified device."""
        target_device = torch.device(device) if isinstance(device, str) else device

        try:
            model.to(target_device)
            if dtype is not None:
                model.to(dtype)
        except NotImplementedError:
            logger.info(
                "[_recursive_to_device] model.to() raised NotImplementedError "
                "(AffineQuantizedTensor on older torch). Moving parameters individually."
            )
            for module in model.modules():
                for param_name, param in module._parameters.items():
                    if param is None:
                        continue
                    if self._is_on_target_device(param, target_device):
                        continue
                    if self._is_quantized_tensor(param):
                        module._parameters[param_name] = self._move_quantized_param(param, target_device)
                    else:
                        module._parameters[param_name] = torch.nn.Parameter(
                            param.data.to(target_device), requires_grad=param.requires_grad
                        )
                        if dtype is not None:
                            module._parameters[param_name] = torch.nn.Parameter(
                                module._parameters[param_name].data.to(dtype),
                                requires_grad=param.requires_grad,
                            )
                for buf_name, buf in module._buffers.items():
                    if buf is not None and not self._is_on_target_device(buf, target_device):
                        module._buffers[buf_name] = buf.to(target_device)

        try:
            self._move_module_recursive(model, target_device, dtype)
        except NotImplementedError:
            pass

        wrong_device_params = []
        for name, param in model.named_parameters():
            if not self._is_on_target_device(param, device):
                wrong_device_params.append(name)

        if wrong_device_params and device != "cpu":
            logger.warning(
                f"[_recursive_to_device] {len(wrong_device_params)} parameters on wrong device after initial move, retrying individually"
            )
            for module in model.modules():
                for param_name, param in module._parameters.items():
                    if param is None or self._is_on_target_device(param, target_device):
                        continue
                    if self._is_quantized_tensor(param):
                        module._parameters[param_name] = self._move_quantized_param(param, target_device)
                    else:
                        module._parameters[param_name] = torch.nn.Parameter(
                            param.data.to(target_device), requires_grad=param.requires_grad
                        )
                        if dtype is not None and module._parameters[param_name].is_floating_point():
                            module._parameters[param_name] = torch.nn.Parameter(
                                module._parameters[param_name].data.to(dtype),
                                requires_grad=param.requires_grad,
                            )

        if device != "cpu":
            self._synchronize()

        if device != "cpu":
            still_wrong = []
            for name, param in model.named_parameters():
                if not self._is_on_target_device(param, device):
                    still_wrong.append(f"{name} on {param.device}")
            if still_wrong:
                logger.error(
                    f"[_recursive_to_device] CRITICAL: {len(still_wrong)} parameters still on wrong device: {still_wrong[:10]}"
                )
