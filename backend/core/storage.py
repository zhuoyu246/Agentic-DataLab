from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from core.context import dataframe_fingerprint, dataframe_profile
from schemas import DatasetMeta, DatasetPreview


class DatasetStorage:
    """
    Hot/cold split for enterprise cost control.

    Hot: in-process dataframe cache for active analysis.
    Cold: parquet/pickle files under tenant-aware storage paths.
    """

    def __init__(self, root: Path, hot_max_mb: int = 64, fmt: str = "parquet") -> None:
        self.root = root
        self.hot_max_bytes = hot_max_mb * 1024 * 1024
        self.fmt = fmt if fmt in {"parquet", "pickle"} else "parquet"
        self.hot: dict[str, pd.DataFrame] = {}
        (self.root / "hot").mkdir(parents=True, exist_ok=True)
        (self.root / "cold").mkdir(parents=True, exist_ok=True)
        (self.root / "meta").mkdir(parents=True, exist_ok=True)

    def register(
        self,
        df: pd.DataFrame,
        *,
        tenant_id: str,
        label: str,
        stage: str = "raw",
        parent_ids: list[str] | None = None,
        created_by: str = "user",
        provenance: dict[str, Any] | None = None,
    ) -> DatasetMeta:
        dataset_id = f"{stage}_{uuid4().hex[:10]}"
        schema_hash, fingerprint = dataframe_fingerprint(df)
        uri = self._write_cold(dataset_id, tenant_id, df)
        hot = int(df.memory_usage(deep=True).sum()) <= self.hot_max_bytes
        if hot:
            self.hot[dataset_id] = df.copy()
        meta = DatasetMeta(
            id=dataset_id,
            label=label,
            stage=stage,
            tenant_id=tenant_id,
            shape=(int(df.shape[0]), int(df.shape[1])),
            columns=[str(c) for c in df.columns],
            schema_hash=schema_hash,
            fingerprint=fingerprint,
            hot=hot,
            uri=uri,
            parent_ids=parent_ids or [],
            created_by=created_by,
            provenance=provenance or {},
        )
        self._write_meta(meta)
        return meta

    def load(self, meta: DatasetMeta) -> pd.DataFrame:
        if meta.id in self.hot:
            return self.hot[meta.id].copy()
        if not meta.uri:
            raise FileNotFoundError(f"dataset {meta.id} has no cold uri")
        path = Path(meta.uri)
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_pickle(path)
        if int(df.memory_usage(deep=True).sum()) <= self.hot_max_bytes:
            self.hot[meta.id] = df.copy()
        return df

    def preview(self, meta: DatasetMeta, rows: int = 50) -> DatasetPreview:
        df = self.load(meta)
        safe = df.head(rows).where(pd.notnull(df.head(rows)), None)
        return DatasetPreview(
            dataset_id=meta.id,
            columns=[str(c) for c in df.columns],
            rows=safe.to_dict(orient="records"),
            shape=(int(df.shape[0]), int(df.shape[1])),
            profile=dataframe_profile(df, sample_rows=min(rows, 20)),
        )

    def _write_cold(self, dataset_id: str, tenant_id: str, df: pd.DataFrame) -> str:
        folder = self.root / "cold" / tenant_id
        folder.mkdir(parents=True, exist_ok=True)
        if self.fmt == "parquet":
            path = folder / f"{dataset_id}.parquet"
            try:
                df.to_parquet(path, index=False)
                return str(path)
            except Exception:
                pass
        path = folder / f"{dataset_id}.pkl"
        df.to_pickle(path)
        return str(path)

    def _write_meta(self, meta: DatasetMeta) -> None:
        folder = self.root / "meta" / meta.tenant_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{meta.id}.json").write_text(
            meta.model_dump_json(indent=2), encoding="utf-8"
        )

    def load_meta(self, tenant_id: str, dataset_id: str) -> DatasetMeta:
        path = self.root / "meta" / tenant_id / f"{dataset_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return DatasetMeta.model_validate(data)

