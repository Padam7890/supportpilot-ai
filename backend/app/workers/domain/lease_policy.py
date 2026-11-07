"""Worker recovery windows shared with Operations monitoring."""

from datetime import timedelta

AI_EXECUTION_LEASE = timedelta(minutes=3)
COMMERCE_ACTION_LEASE = timedelta(minutes=5)
DOCUMENT_INGESTION_LEASE = timedelta(minutes=5)
CATALOG_JOB_LEASE = timedelta(minutes=5)
