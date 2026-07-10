import re


def redact_api_keys(text: str) -> str:
    """Redact likely API keys/tokens/secrets from error text before logging."""
    return re.sub(r'(?i)(key|api[_-]?key|token|secret)(["\s:=]+)([A-Za-z0-9_-]{20,})', r'\1\2***REDACTED***', text)


def classify_http_error(status_code: int) -> str:
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "quota"
    if status_code in (400, 404):
        return "bad_request"
    if status_code >= 500:
        return "server_error"
    return "unknown"


if __name__ == "__main__":
    assert redact_api_keys('token: "abcdefghijklmnopqrst"') == 'token: "***REDACTED***"'
    assert redact_api_keys("no secrets here") == "no secrets here"
    assert classify_http_error(401) == "auth"
    assert classify_http_error(404) == "bad_request"
    assert classify_http_error(429) == "quota"
    assert classify_http_error(500) == "server_error"
    assert classify_http_error(418) == "unknown"
    print("ok")
