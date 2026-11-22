import pytest
from pydantic import ValidationError

from rayohx_api.schemas.v1 import InspectRequest, InspectResponse

URL = "https://example.test/master.m3u8"


def test_request_defaults() -> None:
    request = InspectRequest(url=URL)
    assert request.quality == "best"
    assert request.network.headers == {}


@pytest.mark.parametrize("data", [{"url": ""}, {"url": "u" * 4097}, {"url": URL, "quality": "no"}])
def test_request_rejects_invalid(data: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        InspectRequest.model_validate(data)


def test_response_wraps_plain_data() -> None:
    assert InspectResponse(playlist={"kind": "master", "n": [1]}).playlist["kind"] == "master"
    with pytest.raises(ValidationError):
        InspectResponse(playlist="text")  # type: ignore[arg-type]
