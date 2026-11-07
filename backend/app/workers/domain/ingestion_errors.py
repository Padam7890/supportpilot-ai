"""Public diagnostics for known document ingestion failures."""


class IngestionInputError(ValueError):
    """An input failure with a fixed, safe message."""


ENCRYPTED_PDF = "Encrypted PDF files are not supported"
SOURCE_UNAVAILABLE = "Document source is unavailable for ingestion"
SIZE_LIMIT = "Document exceeds the processing size limit"
NO_SEARCHABLE_TEXT = "No searchable text could be extracted"
LEASE_EXHAUSTED = "Worker lease expired after the retry limit"

INGESTION_ERROR_CODES = {
    ENCRYPTED_PDF: "encrypted_pdf",
    SOURCE_UNAVAILABLE: "source_unavailable",
    SIZE_LIMIT: "document_size_limit",
    NO_SEARCHABLE_TEXT: "no_searchable_text",
    LEASE_EXHAUSTED: "worker_lease_exhausted",
    "UnicodeDecodeError: processing failed": "unsupported_text_encoding",
}

# These failures require a different source, so retrying the same bytes cannot help.
NON_RETRYABLE_INGESTION_CODES = frozenset(INGESTION_ERROR_CODES.values()) - {
    "worker_lease_exhausted",
}


def requires_replacement(last_error: str | None) -> bool:
    return last_error is not None and INGESTION_ERROR_CODES.get(last_error) in NON_RETRYABLE_INGESTION_CODES
