from __future__ import annotations

import hashlib

from schemas import ArtifactEnvelope, DatasetMeta, PipelineEdge, PipelineGraph, PipelineNode


def build_pipeline_graph(
    datasets: dict[str, DatasetMeta],
    active_dataset_id: str | None,
    artifacts: list[ArtifactEnvelope] | None = None,
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
    for artifact in (artifacts or [])[-24:]:
        node_id = f"artifact:{artifact.id}"
        source_dataset_id = artifact.dataset_id if artifact.dataset_id in datasets else active_dataset_id
        nodes.append(
            PipelineNode(
                id=node_id,
                label=artifact.title,
                stage=artifact.kind,
                dataset_id=source_dataset_id,
                status="degraded" if artifact.degraded else "succeeded",
                metrics={"kind": artifact.kind, "degraded": artifact.degraded},
            )
        )
        if source_dataset_id and source_dataset_id in datasets:
            edges.append(
                PipelineEdge(
                    id=f"{source_dataset_id}->{node_id}",
                    source=source_dataset_id,
                    target=node_id,
                    label=artifact.kind,
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
