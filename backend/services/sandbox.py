from __future__ import annotations

import pandas as pd


class SandboxViolation(RuntimeError):
    pass


class PythonSandbox:
    def __init__(self, timeout_seconds: float = 8) -> None:
        self.timeout_seconds = timeout_seconds

    async def run_transform(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        raise SandboxViolation(
            "Arbitrary Python execution is disabled. "
            "Use governed, explicitly implemented data operations instead."
        )
