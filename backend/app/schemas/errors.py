from pydantic import BaseModel


class ProblemDetails(BaseModel):
    """RFC 9457 problem details with a stable SupportPilot error code."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    errors: list[dict[str, object]] | None = None


COMMON_ERROR_RESPONSES = {
    status: {
        "description": "RFC 9457 Problem Details response",
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetails"}
            }
        },
    }
    for status in (400, 401, 403, 404, 409, 413, 415, 422, 429, 500)
}
