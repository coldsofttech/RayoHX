# rayohx-pytest

A pytest plugin with the test support shared by the RayoHX repositories. It is not published to PyPI;
add it to the development dependencies from git:

```toml
[dependency-groups]
dev = ["rayohx-pytest"]

[tool.uv.sources]
rayohx-pytest = { git = "https://github.com/coldsofttech/RayoHX", subdirectory = "packages/pytest", tag = "..." }
```

## Fixtures

- `local_server`: a factory that starts a real HTTP server on `127.0.0.1` and stops it after the test.
  Call it with routes (and `tls=` from `tls_certificate` for HTTPS).
- `tls_certificate`: a self-signed certificate and key (`(cert_path, key_path)`) valid for `127.0.0.1`.
- `ts_payload`: builds MPEG-TS bytes the engine accepts as real segments.

The `rayohx_pytest.site` module has `Site`, an httpx mock handler that serves bytes by path and logs requests, and `hls_site` and `single_file_site`, which build streams from the shared media fixtures.

The classes and helpers behind them (`Reply`, `Seen`, `LocalServer`, `vod_routes` and the fixture
readers) are importable from `rayohx_pytest.servers`, `rayohx_pytest.hls` and `rayohx_pytest.fixtures`.
