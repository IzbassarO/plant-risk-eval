"""Model factory and accelerator selection for the ICA 2026 experiments.

Three ImageNet-pretrained backbones with their classifier head replaced by a
fresh linear layer sized to the task. Backbone choice is the only architectural
variable in the experiment matrix; everything else is held constant.
"""
from __future__ import annotations

import platform
from dataclasses import dataclass, asdict
from typing import Callable

import torch
import torch.nn as nn
import torchvision
from torchvision import models as tvm

MODEL_NAMES = ("resnet50", "efficientnet_b0", "mobilenet_v3_small")


@dataclass(frozen=True)
class HardwareInfo:
    device: str
    backend: str
    torch_version: str
    torchvision_version: str
    platform: str
    machine: str
    cuda_device_name: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def select_device(preferred: str = "auto") -> HardwareInfo:
    """Resolve the accelerator in the required priority: CUDA -> MPS -> CPU."""
    if preferred not in ("auto", "cuda", "mps", "cpu"):
        raise ValueError(f"unknown device preference {preferred!r}")

    def _info(device: str, backend: str, name: str | None = None) -> HardwareInfo:
        return HardwareInfo(
            device=device,
            backend=backend,
            torch_version=torch.__version__,
            torchvision_version=torchvision.__version__,
            platform=platform.platform(),
            machine=platform.machine(),
            cuda_device_name=name,
        )

    if preferred in ("auto", "cuda") and torch.cuda.is_available():
        return _info("cuda", "cuda", torch.cuda.get_device_name(0))
    if preferred == "cuda":
        raise RuntimeError("CUDA requested but unavailable")

    mps_ok = torch.backends.mps.is_available() and torch.backends.mps.is_built()
    if preferred in ("auto", "mps") and mps_ok:
        return _info("mps", "mps")
    if preferred == "mps":
        raise RuntimeError("MPS requested but unavailable")

    return _info("cpu", "cpu")


def _replace_head(model: nn.Module, name: str, num_classes: int) -> nn.Module:
    if name == "resnet50":
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif name in ("efficientnet_b0", "mobilenet_v3_small"):
        last = model.classifier[-1]
        model.classifier[-1] = nn.Linear(last.in_features, num_classes)
    else:  # pragma: no cover - guarded by build_model
        raise ValueError(name)
    return model


def build_model(name: str, num_classes: int, pretrained: bool = True) -> nn.Module:
    """Construct a backbone with an ImageNet initialisation and a fresh head."""
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown model {name!r}; expected one of {MODEL_NAMES}")

    builders: dict[str, tuple[Callable, object]] = {
        "resnet50": (tvm.resnet50, tvm.ResNet50_Weights.IMAGENET1K_V2),
        "efficientnet_b0": (tvm.efficientnet_b0, tvm.EfficientNet_B0_Weights.IMAGENET1K_V1),
        "mobilenet_v3_small": (tvm.mobilenet_v3_small, tvm.MobileNet_V3_Small_Weights.IMAGENET1K_V1),
    }
    fn, weights = builders[name]
    model = fn(weights=weights if pretrained else None)
    return _replace_head(model, name, num_classes)


def pretrained_weight_id(name: str) -> str:
    """The exact ImageNet checkpoint enum used, recorded in run metadata."""
    return {
        "resnet50": "ResNet50_Weights.IMAGENET1K_V2",
        "efficientnet_b0": "EfficientNet_B0_Weights.IMAGENET1K_V1",
        "mobilenet_v3_small": "MobileNet_V3_Small_Weights.IMAGENET1K_V1",
    }[name]


def count_parameters(model: nn.Module) -> dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total_parameters": total, "trainable_parameters": trainable}


def peak_memory_bytes(device: str) -> int | None:
    """Peak allocator memory, where the backend exposes it."""
    if device == "cuda":
        return int(torch.cuda.max_memory_allocated())
    if device == "mps":
        driver = getattr(torch.mps, "driver_allocated_memory", None)
        if callable(driver):
            return int(driver())
    return None


def reset_peak_memory(device: str) -> None:
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
