"""
DataWranglingAgent — Merge, join, concat, aggregate and reshape datasets.

Handles multi-dataset operations with production-grade strategy selection.
"""
from __future__ import annotations

import pandas as pd

from agents.base import AgentContext, AgentResult, BaseAgent
from schemas import ArtifactEnvelope

WRANGLING_PROMPT = """\
You are an expert data wrangling specialist. Your task is to transform
and combine datasets using the optimal strategy:

1. **Merge/Join**: When datasets share common keys, perform appropriate join
   (inner, left, right, outer) based on the relationship
2. **Concatenation**: Stack datasets vertically when they share the same schema
3. **Aggregation**: Group-by operations for summary statistics
4. **Reshaping**: Pivot/unpivot operations for structural transformation
5. **Type Normalization**: Convert low-cardinality string columns to category dtype

Always report the operation performed and resulting dataset shape.
"""


class DataWranglingAgent(BaseAgent):
    name = "data_wrangling_agent"
    description = "Merge, join, concat, aggregate and reshape datasets."

    async def run(self, ctx: AgentContext, instruction: str) -> AgentResult:
        await ctx.emit("Running deterministic wrangling.", agent_name=self.name)
        ids = [did for did in ctx.datasets if did in instruction]
        if len(ids) >= 2:
            left_meta, right_meta = ctx.datasets[ids[0]], ctx.datasets[ids[1]]
            left, right = ctx.storage.load(left_meta), ctx.storage.load(right_meta)
            common = [c for c in left.columns if c in set(right.columns)]
            if common and "concat" not in instruction.lower():
                out = pd.merge(left, right, on=common[0], how="left", suffixes=("_left", "_right"))
                op = f"left join on {common[0]}"
            else:
                out = pd.concat([left, right], axis=0, ignore_index=True)
                op = "concat rows"
            parents = [left_meta.id, right_meta.id]
        else:
            meta, df = ctx.active_dataframe()
            out = df.copy()
            op = "type normalization"
            parents = [meta.id]
            for col in out.select_dtypes(include=["object", "string"]).columns:
                nunique = out[col].nunique(dropna=True)
                if nunique <= max(32, int(len(out) * 0.05)):
                    out[col] = out[col].astype("category")
        new_meta = ctx.storage.register(
            out,
            tenant_id=ctx.tenant.tenant_id,
            label="wrangled dataset",
            stage="wrangled",
            parent_ids=parents,
            created_by=self.name,
            provenance={"source_type": "agent", "transform": op},
        )
        return AgentResult(
            message=f"Wrangling complete: {op}.",
            datasets={new_meta.id: new_meta},
            active_dataset_id=new_meta.id,
            artifacts=[
                ArtifactEnvelope(
                    kind="wrangling_report",
                    title="Wrangling report",
                    dataset_id=new_meta.id,
                    payload={"operation": op, "parents": parents, "shape": new_meta.shape},
                )
            ],
        )
