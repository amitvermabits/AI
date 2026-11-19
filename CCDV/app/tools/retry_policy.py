
"""
AI Travel Buddy - Retry Policy Lab.

Certifications:
    CCDV-F: Agent loop error handling.
    CCAR-F: Failure recovery and retry budgets.

Purpose:
    Decide whether an HTTP 429 request may be retried
    and how long to wait before another attempt.

Scope:
    This lab handles HTTP 429 only.
    No real HTTP requests or waiting are performed.

Run:
    uv run python -m app.tools.retry_policy
"""


def get_retry_delay(
    status_code: int,
    attempt: int,
    retry_after: int | None = None,
    max_attempts: int = 3,
) -> int | None:
    """
    Calculate a retry delay for HTTP 429.

    Args:
        status_code: HTTP response status.
        attempt: Number of the attempt that just failed.
        retry_after: Minimum wait in seconds, if provided.
        max_attempts: Maximum total requests allowed.

    Returns:
        Wait time in seconds, or None if no retry is allowed.

    Note:
        This initial deterministic version does not add
        jitter. We'll introduce that separately.
    """

    if status_code != 429:
        return None

    # Stop when our total attempt budget is exhausted.
    if attempt >= max_attempts:
        return None

    # Basic exponential backoff: 1, 2, 4, 8 ...
    backoff = 2 ** (attempt - 1)

    # Honor the server's minimum wait when supplied.
    return max(backoff, retry_after or 0)



def build_retry_exhausted_result(
    tool_name: str,
    attempts: int,
) -> dict[str, str | int]:
    """
    Build a structured error after retry exhaustion.

    Args:
        tool_name: Name of the failed search tool.
        attempts: Total number of attempts made.

    Returns:
        An error dictionary suitable for returning
        to Claude as a tool_result.

    Important:
        This function performs no retries or API calls.
        It only describes an exhausted retry budget.
    """
    return {
        "status": "error",
        "error": "rate_limit_exhausted",
        "tool": tool_name,
        "http_status": 429,
        "attempts": attempts,
        "message": (
            "Provider rate limit prevented "
            "completing the transport search."
        ),
    }


if __name__ == "__main__":
    print(build_retry_exhausted_result("search_trains", 3))
