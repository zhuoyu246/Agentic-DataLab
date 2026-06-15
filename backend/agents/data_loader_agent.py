"""
DataLoaderAgent — File loading with validation and state isolation.

Loads CSV/Excel/Parquet files into the tenant dataset registry.
Results are written to the physically isolated 'data_raw' state slot.
Includes file size and type pre-validation to prevent malicious uploads.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

DATA_LOADER_PROMPT = """\
You are a data loading specialist. Your task is to:
1. Extract the file path from the user's instruction
2. Validate the file exists and is a supported format (CSV, Excel, Parquet)
3. Load the data into a Pandas DataFrame
4. Register it in the workspace with appropriate metadata
5. Report the shape, column names, and data types

Supported formats: .csv, .txt, .xlsx, .xls, .parquet
Maximum file size: 500MB
"""

MAX_FILE_SIZE_MB: int = 500


class DataLoaderAgent(BaseAgent):
    name = "data_loader_agent"
    description = "Load CSV/Excel/Parquet files into the tenant dataset registry."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        await ctx.emit("Resolving file path for data loading.", agent_name=self.name)
        path = self._extract_path(instruction)
        if not path:
            return AgentResult(
                message="No local file path was provided. Upload a dataset or provide a path.",
                degraded=True,
            )
        p = Path(path)

        # Pre-validation: existence check
        if not p.exists():
            raise FileNotFoundError(f"Dataset path does not exist: {p}")

        # Pre-validation: file size check (prevent malicious large uploads)
        file_size_mb = p.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            return AgentResult(
                message=f"File too large ({file_size_mb:.1f}MB). Maximum is {MAX_FILE_SIZE_MB}MB.",
                degraded=True,
            )

        # Load based on file extension
        if p.suffix.lower() in {".csv", ".txt"}:
            df = pd.read_csv(p)
        elif p.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(p)
        elif p.suffix.lower() == ".parquet":
            df = pd.read_parquet(p)
        else:
            raise ValueError(f"Unsupported data file: {p.suffix}")

        meta = ctx.storage.register(
            df,
            tenant_id=ctx.tenant.tenant_id,
            label=p.name,
            stage="raw",
            created_by=ctx.tenant.user_id,
            provenance={"source_type": "file", "source": str(p.resolve())},
        )
        return AgentResult(
            message=f"Loaded `{p.name}` with shape {df.shape}.",
            datasets={meta.id: meta},
            active_dataset_id=meta.id,
            artifacts=[
                ArtifactEnvelope(
                    kind="dataset_profile",
                    title="Loaded dataset profile",
                    dataset_id=meta.id,
                    payload={"shape": meta.shape, "columns": meta.columns},
                )
            ],
        )

    @staticmethod
    def _extract_path(text: str) -> str | None:
        import re
        quoted = re.search(r"['\"`](.+?\.(?:csv|xlsx|xls|parquet))['\"`]", text, re.I)
        if quoted:
            return quoted.group(1)
        plain = re.search(
            r"([A-Za-z]:\\[^\n]+?\.(?:csv|xlsx|xls|parquet)|[./~\w-]+?\.(?:csv|xlsx|xls|parquet))",
            text, re.I,
        )
        return plain.group(1) if plain else None
