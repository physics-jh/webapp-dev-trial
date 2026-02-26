"""
StorageBackend 추상 레이어
DB 교체 시 config.py의 STORAGE_BACKEND 값만 변경
"""

from __future__ import annotations
import os
import logging
from abc import ABC, abstractmethod
import pandas as pd

logger = logging.getLogger(__name__)


# ─── 추상 베이스 ──────────────────────────────────────────────

class BaseStorage(ABC):

    @abstractmethod
    def save(self, df: pd.DataFrame, table: str, **kwargs) -> None:
        ...

    @abstractmethod
    def load(self, table: str, **filters) -> pd.DataFrame:
        ...

    @abstractmethod
    def append(self, df: pd.DataFrame, table: str) -> None:
        ...

    @abstractmethod
    def exists(self, table: str) -> bool:
        ...


# ─── Parquet 구현체 (프로토타입) ──────────────────────────────

class ParquetStorage(BaseStorage):

    def __init__(self, base_dir: str | None = None):
        from config import DATA_PROCESSED
        self.base_dir = base_dir or DATA_PROCESSED
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, table: str) -> str:
        return os.path.join(self.base_dir, f"{table}.parquet")

    def save(self, df: pd.DataFrame, table: str, **kwargs) -> None:
        path = self._path(table)
        df.to_parquet(path, **kwargs)
        logger.info(f"저장 완료: {path} ({len(df):,}행)")

    def load(self, table: str, **filters) -> pd.DataFrame:
        path = self._path(table)
        if not os.path.exists(path):
            raise FileNotFoundError(f"파일 없음: {path}")
        df = pd.read_parquet(path)
        for col, val in filters.items():
            if col in df.columns:
                df = df[df[col] == val]
        return df

    def append(self, df: pd.DataFrame, table: str) -> None:
        if self.exists(table):
            existing = self.load(table)
            df = pd.concat([existing, df]).drop_duplicates()
        self.save(df, table)

    def exists(self, table: str) -> bool:
        return os.path.exists(self._path(table))


# ─── PostgreSQL 스텁 (실전) ───────────────────────────────────

class PostgresStorage(BaseStorage):
    """실전 전환용 — STORAGE_BACKEND=postgres 설정 후 사용"""

    def __init__(self):
        from config import DATA_PROCESSED
        import sqlalchemy as sa
        db_url = os.getenv("DATABASE_URL", "postgresql://localhost/quantvision")
        self.engine = sa.create_engine(db_url)

    def save(self, df: pd.DataFrame, table: str, **kwargs) -> None:
        df.to_sql(table, self.engine, if_exists="replace", index=True, **kwargs)
        logger.info(f"PostgreSQL 저장: {table} ({len(df):,}행)")

    def load(self, table: str, **filters) -> pd.DataFrame:
        query = f"SELECT * FROM {table}"
        df = pd.read_sql(query, self.engine, index_col="index")
        for col, val in filters.items():
            if col in df.columns:
                df = df[df[col] == val]
        return df

    def append(self, df: pd.DataFrame, table: str) -> None:
        df.to_sql(table, self.engine, if_exists="append", index=True)

    def exists(self, table: str) -> bool:
        import sqlalchemy as sa
        return sa.inspect(self.engine).has_table(table)


# ─── 팩토리 ──────────────────────────────────────────────────

def get_storage() -> BaseStorage:
    from config import STORAGE_BACKEND
    backends = {
        "parquet":  ParquetStorage,
        "postgres": PostgresStorage,
    }
    cls = backends.get(STORAGE_BACKEND)
    if cls is None:
        raise ValueError(f"알 수 없는 STORAGE_BACKEND: {STORAGE_BACKEND}")
    return cls()
