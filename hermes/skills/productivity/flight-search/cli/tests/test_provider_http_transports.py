from __future__ import annotations

import gzip
import json
import unittest
from collections.abc import Callable
from unittest.mock import patch

import httpx2

from flights_cli import __version__
from flights_cli.config import KUPIBILET_HEADERS
from flights_cli.errors import CliError
from flights_cli.providers.kupibilet_transport import post_kupibilet_search
from flights_cli.providers.static_catalog import default_fetch_url

HTTPX_CLIENT = httpx2.Client


class ProviderHttpTransportTests(unittest.TestCase):
    @staticmethod
    def client_patch(
        target: str,
        handler: Callable[[httpx2.Request], httpx2.Response],
        constructor_calls: list[dict[str, object]],
    ):
        def build_client(**kwargs: object) -> httpx2.Client:
            constructor_calls.append(kwargs)
            return HTTPX_CLIENT(transport=httpx2.MockTransport(handler), **kwargs)

        return patch(target, side_effect=build_client)

    def test_static_catalog_get_redirect_matrix(self) -> None:
        for redirect_status in (301, 302, 303, 307, 308):
            with self.subTest(redirect_status=redirect_status):
                requests: list[dict[str, object]] = []
                constructors: list[dict[str, object]] = []

                def handler(request: httpx2.Request) -> httpx2.Response:
                    requests.append(
                        {
                            "method": request.method,
                            "path": request.url.path,
                            "content": request.content,
                            "headers": dict(request.headers),
                        }
                    )
                    if request.url.path == "/start":
                        return httpx2.Response(
                            redirect_status, headers={"Location": "/final"}
                        )
                    return httpx2.Response(200, content=b'[{"code":"SVX"}]')

                with self.client_patch(
                    "flights_cli.providers.static_catalog.httpx2.Client",
                    handler,
                    constructors,
                ):
                    result = default_fetch_url("https://catalog.test/start", 17)

                self.assertEqual(result, b'[{"code":"SVX"}]')
                self.assertEqual(
                    [(item["method"], item["path"]) for item in requests],
                    [("GET", "/start"), ("GET", "/final")],
                )
                self.assertEqual(requests[0]["content"], b"")
                self.assertEqual(requests[0]["headers"]["accept"], "application/json")
                self.assertEqual(
                    requests[0]["headers"]["user-agent"],
                    f"flights-cli/{__version__}",
                )
                self.assertEqual(
                    constructors,
                    [
                        {
                            "timeout": 17,
                            "follow_redirects": True,
                            "max_redirects": 10,
                        }
                    ],
                )

    def test_kupibilet_post_redirect_matrix(self) -> None:
        payload = {"trips": [{"departure": "SVX", "arrival": "MOW"}]}
        expected_body = json.dumps(payload).encode("utf-8")

        for redirect_status in (301, 302, 303, 307, 308):
            with self.subTest(redirect_status=redirect_status):
                requests: list[dict[str, object]] = []
                constructors: list[dict[str, object]] = []

                def handler(request: httpx2.Request) -> httpx2.Response:
                    requests.append(
                        {
                            "method": request.method,
                            "path": request.url.path,
                            "content": request.content,
                            "headers": dict(request.headers),
                        }
                    )
                    if len(requests) == 1:
                        return httpx2.Response(
                            redirect_status,
                            headers={"Location": "/middle", "Retry-After": "7"},
                            content=b"redirect",
                        )
                    if len(requests) == 2:
                        return httpx2.Response(302, headers={"Location": "/final"})
                    return httpx2.Response(200, json={"variants": []})

                with self.client_patch(
                    "flights_cli.providers.kupibilet_transport.httpx2.Client",
                    handler,
                    constructors,
                ):
                    if redirect_status in {301, 302, 303}:
                        result, status = post_kupibilet_search(payload, timeout=23)
                        self.assertEqual(result, {"variants": []})
                        self.assertEqual(status, 200)
                        self.assertEqual(
                            [item["method"] for item in requests],
                            ["POST", "GET", "GET"],
                        )
                        for redirected in requests[1:]:
                            self.assertEqual(redirected["content"], b"")
                            self.assertNotIn("content-type", redirected["headers"])
                            self.assertNotIn("content-length", redirected["headers"])
                    else:
                        with self.assertRaises(CliError) as error:
                            post_kupibilet_search(payload, timeout=23)
                        self.assertEqual(len(requests), 1)
                        self.assertEqual(requests[0]["method"], "POST")
                        self.assertEqual(error.exception.error_type, "upstream_error")
                        self.assertEqual(
                            error.exception.details,
                            {"http_status": redirect_status, "retry_after": "7"},
                        )

                self.assertEqual(requests[0]["content"], expected_body)
                self.assertEqual(
                    requests[0]["headers"]["content-type"],
                    KUPIBILET_HEADERS["Content-Type"],
                )
                self.assertEqual(
                    constructors, [{"timeout": 23, "follow_redirects": False}]
                )

    def test_static_catalog_redirect_limit_maps_to_cli_error(self) -> None:
        requests: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            requests.append(request)
            return httpx2.Response(302, headers={"Location": "/loop"})

        with self.client_patch(
            "flights_cli.providers.static_catalog.httpx2.Client",
            handler,
            [],
        ):
            with self.assertRaises(CliError) as error:
                default_fetch_url("https://catalog.test/start", 10)

        self.assertEqual(
            error.exception.message,
            "static catalog request failed: TooManyRedirects",
        )
        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertIsNone(error.exception.details)
        self.assertEqual(len(requests), 11)
        self.assertTrue(all(request.method == "GET" for request in requests))

    def test_kupibilet_subsequent_redirect_limit_maps_to_cli_error(self) -> None:
        request_methods: list[str] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            request_methods.append(request.method)
            return httpx2.Response(302, headers={"Location": "/loop"})

        with self.client_patch(
            "flights_cli.providers.kupibilet_transport.httpx2.Client",
            handler,
            [],
        ):
            with self.assertRaises(CliError) as error:
                post_kupibilet_search({}, timeout=10)

        self.assertEqual(
            error.exception.message,
            "Kupibilet request failed: TooManyRedirects: "
            "Exceeded maximum allowed redirects.",
        )
        self.assertEqual(error.exception.error_type, "upstream_error")
        self.assertIsNone(error.exception.details)
        self.assertEqual(request_methods[0], "POST")
        self.assertGreater(len(request_methods), 2)
        self.assertTrue(all(method == "GET" for method in request_methods[1:]))

    def test_automatic_gzip_decoding_and_success_bytes(self) -> None:
        catalog_raw = b'[{"code":"SVX"}]'
        kupibilet_raw = b'{"variants":[]}'

        def catalog_handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                content=gzip.compress(catalog_raw),
                headers={"Content-Encoding": "gzip"},
            )

        with self.client_patch(
            "flights_cli.providers.static_catalog.httpx2.Client",
            catalog_handler,
            [],
        ):
            self.assertEqual(
                default_fetch_url("https://catalog.test/data", 10), catalog_raw
            )

        def kupibilet_handler(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                content=gzip.compress(kupibilet_raw),
                headers={"Content-Encoding": "gzip"},
            )

        with self.client_patch(
            "flights_cli.providers.kupibilet_transport.httpx2.Client",
            kupibilet_handler,
            [],
        ):
            self.assertEqual(
                post_kupibilet_search({}, timeout=10), ({"variants": []}, 200)
            )

    def test_http_error_shapes_retry_after_and_unicode_truncation(self) -> None:
        body = "я" * 1100
        for status in (400, 500):
            with self.subTest(transport="kupibilet", status=status):

                def kupibilet_handler(request: httpx2.Request) -> httpx2.Response:
                    return httpx2.Response(
                        status,
                        text=body,
                        headers={"Retry-After": "120"},
                    )

                with self.client_patch(
                    "flights_cli.providers.kupibilet_transport.httpx2.Client",
                    kupibilet_handler,
                    [],
                ):
                    with self.assertRaises(CliError) as error:
                        post_kupibilet_search({}, timeout=10)
                prefix = f"Kupibilet HTTP {status}: "
                self.assertTrue(error.exception.message.startswith(prefix))
                self.assertEqual(
                    len(error.exception.message.removeprefix(prefix)), 1000
                )
                self.assertEqual(error.exception.error_type, "upstream_error")
                self.assertEqual(
                    error.exception.details,
                    {"http_status": status, "retry_after": "120"},
                )

            with self.subTest(transport="static_catalog", status=status):

                def catalog_handler(request: httpx2.Request) -> httpx2.Response:
                    return httpx2.Response(status, text=body)

                with self.client_patch(
                    "flights_cli.providers.static_catalog.httpx2.Client",
                    catalog_handler,
                    [],
                ):
                    with self.assertRaises(CliError) as error:
                        default_fetch_url("https://catalog.test/data", 10)
                prefix = f"static catalog HTTP {status}: "
                self.assertTrue(error.exception.message.startswith(prefix))
                self.assertEqual(
                    len(error.exception.message.removeprefix(prefix)), 1000
                )
                self.assertEqual(error.exception.error_type, "upstream_error")
                self.assertIsNone(error.exception.details)

    def test_kupibilet_rejects_malformed_and_non_object_json(self) -> None:
        for raw, expected_prefix in (
            (b"{", "Kupibilet request failed: JSONDecodeError:"),
            (b"[]", "Kupibilet response must be a JSON object"),
        ):
            with self.subTest(raw=raw):

                def handler(request: httpx2.Request) -> httpx2.Response:
                    return httpx2.Response(200, content=raw)

                with self.client_patch(
                    "flights_cli.providers.kupibilet_transport.httpx2.Client",
                    handler,
                    [],
                ):
                    with self.assertRaises(CliError) as error:
                        post_kupibilet_search({}, timeout=10)
                self.assertTrue(error.exception.message.startswith(expected_prefix))
                self.assertEqual(error.exception.error_type, "upstream_error")

    def test_timeout_connect_and_transport_errors_map_to_cli_error(self) -> None:
        for exception_type in (
            httpx2.ConnectTimeout,
            httpx2.ConnectError,
            httpx2.ReadError,
        ):
            with self.subTest(transport="kupibilet", error=exception_type.__name__):

                def kupibilet_handler(request: httpx2.Request) -> httpx2.Response:
                    raise exception_type("offline", request=request)

                with self.client_patch(
                    "flights_cli.providers.kupibilet_transport.httpx2.Client",
                    kupibilet_handler,
                    [],
                ):
                    with self.assertRaises(CliError) as error:
                        post_kupibilet_search({}, timeout=10)
                self.assertTrue(
                    error.exception.message.startswith(
                        f"Kupibilet request failed: {exception_type.__name__}:"
                    )
                )
                self.assertEqual(error.exception.error_type, "upstream_error")

            with self.subTest(
                transport="static_catalog", error=exception_type.__name__
            ):

                def catalog_handler(request: httpx2.Request) -> httpx2.Response:
                    raise exception_type("offline", request=request)

                with self.client_patch(
                    "flights_cli.providers.static_catalog.httpx2.Client",
                    catalog_handler,
                    [],
                ):
                    with self.assertRaises(CliError) as error:
                        default_fetch_url("https://catalog.test/data", 10)
                self.assertEqual(
                    error.exception.message,
                    f"static catalog request failed: {exception_type.__name__}",
                )
                self.assertEqual(error.exception.error_type, "upstream_error")


if __name__ == "__main__":
    unittest.main()
