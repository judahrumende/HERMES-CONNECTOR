import httpx
import pytest

from hermes_jarvis.hermes import HermesClient, HermesError


@pytest.mark.asyncio
async def test_probe_preserves_optional_endpoint_failures():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health/detailed":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "default"}]})
        return httpx.Response(404, json={"detail": "not available"})

    client = HermesClient("http://hermes.test")
    await client.client.aclose()
    client.client = httpx.AsyncClient(base_url="http://hermes.test", transport=httpx.MockTransport(handler))
    observed = await client.probe()
    await client.close()
    assert observed["health"] == {"status": "ok"}
    assert observed["models"]["data"][0]["id"] == "default"
    assert "capabilities unavailable" in observed["warnings"]
    assert "jobs unavailable" in observed["warnings"]


@pytest.mark.asyncio
async def test_run_rejects_invalid_upstream_shape():
    client = HermesClient("http://hermes.test")
    await client.client.aclose()
    client.client = httpx.AsyncClient(base_url="http://hermes.test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    with pytest.raises(HermesError):
        await client.create_run({"input": "hello"})
    await client.close()
