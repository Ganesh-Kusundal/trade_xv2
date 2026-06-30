"""Datalake storage — data access layer."""

from datalake.storage.catalog import DataCatalog as DataCatalog
from datalake.storage.parquet_store import ParquetStore as ParquetStore
from datalake.storage.views import create_views as create_views
