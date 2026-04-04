from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn
import yaml
from torchvision import transforms


class Flatten(nn.Module):
    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return inputs.view(inputs.size(0), -1)


class BasicBlockIR(nn.Module):
    def __init__(self, in_channels: int, depth: int, stride: int) -> None:
        super().__init__()
        if in_channels == depth:
            self.shortcut_layer = nn.MaxPool2d(1, stride)
        else:
            self.shortcut_layer = nn.Sequential(
                nn.Conv2d(in_channels, depth, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(depth),
            )
        self.res_layer = nn.Sequential(
            nn.BatchNorm2d(in_channels),
            nn.Conv2d(in_channels, depth, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(depth),
            nn.PReLU(depth),
            nn.Conv2d(depth, depth, kernel_size=3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(depth),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.res_layer(inputs) + self.shortcut_layer(inputs)


@dataclass(frozen=True)
class Bottleneck:
    in_channels: int
    depth: int
    stride: int


def _get_block(in_channels: int, depth: int, num_units: int, stride: int = 2) -> list[Bottleneck]:
    return [Bottleneck(in_channels, depth, stride)] + [
        Bottleneck(depth, depth, 1) for _ in range(num_units - 1)
    ]


def _get_blocks(num_layers: int) -> list[list[Bottleneck]]:
    if num_layers == 18:
        return [
            _get_block(64, 64, 2),
            _get_block(64, 128, 2),
            _get_block(128, 256, 2),
            _get_block(256, 512, 2),
        ]
    if num_layers == 50:
        return [
            _get_block(64, 64, 3),
            _get_block(64, 128, 4),
            _get_block(128, 256, 14),
            _get_block(256, 512, 3),
        ]
    if num_layers == 100:
        return [
            _get_block(64, 64, 3),
            _get_block(64, 128, 13),
            _get_block(128, 256, 30),
            _get_block(256, 512, 3),
        ]
    raise ValueError(f"Unsupported AdaFace iResNet depth: {num_layers}")


class AdaFaceIResNet(nn.Module):
    def __init__(self, input_size: int, num_layers: int, output_dim: int = 512) -> None:
        super().__init__()
        if input_size not in (112, 224):
            raise ValueError("input_size should be 112 or 224")

        self.input_layer = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.PReLU(64),
        )

        modules: list[nn.Module] = []
        for block in _get_blocks(num_layers):
            for bottleneck in block:
                modules.append(BasicBlockIR(bottleneck.in_channels, bottleneck.depth, bottleneck.stride))
        self.body = nn.Sequential(*modules)

        output_spatial = 7 if input_size == 112 else 14
        self.output_layer = nn.Sequential(
            nn.BatchNorm2d(512),
            nn.Dropout(0.4),
            Flatten(),
            nn.Linear(512 * output_spatial * output_spatial, output_dim),
            nn.BatchNorm1d(output_dim, affine=False),
        )

        self._initialize_weights()

    def _initialize_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.constant_(module.weight, 1.0)
                nn.init.constant_(module.bias, 0.0)
            elif isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0.0)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        features = self.input_layer(inputs)
        features = self.body(features)
        return self.output_layer(features)


@dataclass(frozen=True)
class AdaFaceBundle:
    model: nn.Module
    transform: transforms.Compose
    color_space: str


def load_adaface_bundle(
    config_path: Path,
    weights_path: Path,
    *,
    device_name: str,
) -> AdaFaceBundle:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    model_name = str(config.get("name", "ir50")).strip().lower()
    output_dim = int(config.get("output_dim", 512))
    input_size = int(config.get("input_size", [3, 112, 112])[-1])
    color_space = str(config.get("color_space", "RGB")).strip().upper()

    if model_name == "ir18":
        model = AdaFaceIResNet(input_size=input_size, num_layers=18, output_dim=output_dim)
    elif model_name == "ir50":
        model = AdaFaceIResNet(input_size=input_size, num_layers=50, output_dim=output_dim)
    elif model_name == "ir101":
        model = AdaFaceIResNet(input_size=input_size, num_layers=100, output_dim=output_dim)
    else:
        raise ValueError(f"Unsupported AdaFace model name: {model_name}")

    state_dict = _normalize_state_dict(torch.load(weights_path, map_location="cpu"))
    result = model.load_state_dict(state_dict, strict=False)
    missing_keys = [key for key in result.missing_keys if not key.endswith("num_batches_tracked")]
    if missing_keys:
        raise RuntimeError(f"AdaFace model missing keys: {missing_keys}")

    device = _resolve_device(device_name)
    model.eval()
    model.to(device)
    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ]
    )
    return AdaFaceBundle(model=model, transform=transform, color_space=color_space)


def _resolve_device(device_name: str) -> torch.device:
    normalized = (device_name or "cpu").strip().lower()
    if normalized.startswith("cuda") and torch.cuda.is_available():
        return torch.device(normalized)
    return torch.device("cpu")


def _normalize_state_dict(state_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    if not state_dict:
        return state_dict
    prefixes = ("net.", "model.")
    normalized: dict[str, torch.Tensor] = {}
    for key, value in state_dict.items():
        next_key = key
        for prefix in prefixes:
            if next_key.startswith(prefix):
                next_key = next_key[len(prefix) :]
                break
        normalized[next_key] = value
    return normalized
