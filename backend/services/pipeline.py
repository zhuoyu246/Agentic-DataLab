from __future__ import annotations

import hashlib

from schemas import DatasetMeta, PipelineEdge, PipelineGraph, PipelineNode


def build_pipeline_graph(
    datasets: dict[str, DatasetMeta], active_dataset_id: str | None
) -> PipelineGraph:
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    for dataset_id, meta in datasets.items():
        nodes.append(
            PipelineNode(
                id=dataset_id,
                label=meta.label,
                stage=meta.stage,
                dataset_id=dataset_id,
                metrics={"shape": list(meta.shape), "hot": meta.hot},
            )
        )
        for parent_id in meta.parent_ids:
            if parent_id in datasets:
                edges.append(
                    PipelineEdge(
                        id=f"{parent_id}->{dataset_id}",
                        source=parent_id,
                        target=dataset_id,
                        label=meta.stage,
                    )
                )
    signature = "|".join(
        [f"{n.id}:{n.stage}:{n.label}" for n in nodes]
        + [f"{e.source}->{e.target}" for e in edges]
    )
    pipeline_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return PipelineGraph(
        nodes=nodes,
        edges=edges,
        active_dataset_id=active_dataset_id,
        pipeline_hash=pipeline_hash,
    )

