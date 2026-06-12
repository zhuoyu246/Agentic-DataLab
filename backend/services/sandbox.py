from __future__ import annotations

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd


class SandboxViolation(RuntimeError):
    pass


class PythonSandbox:
    BLOCKED_IMPORTS = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "requests",
        "httpx",
    }

    def __init__(self, timeout_seconds: float = 8) -> None:
        self.timeout_seconds = timeout_seconds
        self._pool = ThreadPoolExecutor(max_workers=2)

    async def run_transform(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        self._validate(code)
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._pool, self._execute, code, df.copy()),
            timeout=self.timeout_seconds,
        )

    def _validate(self, code: str) -> None:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in self.BLOCKED_IMPORTS:
                        raise SandboxViolation(f"Blocked import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in self.BLOCKED_IMPORTS:
                    raise SandboxViolation(f"Blocked import: {node.module}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec", "compile", "open", "__import__"}:
                    raise SandboxViolation(f"Blocked call: {node.func.id}")

    @staticmethod
    def _execute(code: str, df: pd.DataFrame) -> pd.DataFrame:
        env: dict[str, Any] = {"pd": pd}
        exec(code, env, env)
        fn = env.get("transform")
        if not callable(fn):
            raise SandboxViolation("Code must define `transform(df) -> DataFrame`.")
        out = fn(df)
        if not isinstance(out, pd.DataFrame):
            raise SandboxViolation("Transform did not return a DataFrame.")
        return out

