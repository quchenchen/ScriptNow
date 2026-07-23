from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    api_key: str = ""
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "deepseek-v4-pro"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


runtime_config = RuntimeConfig(
    api_key=os.getenv("SCRIPTFLOW_API_KEY", ""),
    api_base=os.getenv("SCRIPTFLOW_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    model=os.getenv("SCRIPTFLOW_MODEL", "deepseek-v4-pro"),
)
