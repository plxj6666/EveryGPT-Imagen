#!/usr/bin/env python3
"""Generate or edit images through the EveryGPT OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import http.client
import ipaddress
import json
import mimetypes
import os
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.everygpt.site/v1"
LOCAL_CONFIG_NAME = "local_config.json"
ASPECT_RATIOS = ("1:1", "3:4", "4:3", "9:16", "16:9")
MODEL_SIZES = {
    "gpt-image2-1k": {
        "1:1": "1024x1024", "3:4": "768x1024", "4:3": "1024x768",
        "9:16": "576x1024", "16:9": "1024x576",
    },
    "gpt-image2-2k": {
        "1:1": "2048x2048", "3:4": "1536x2048", "4:3": "2048x1536",
        "9:16": "1152x2048", "16:9": "2048x1152",
    },
    "gpt-image2-4k": {
        "1:1": "4096x4096", "3:4": "3072x4096", "4:3": "4096x3072",
        "9:16": "2160x3840", "16:9": "3840x2160",
    },
}
USER_AGENT = "everygpt-image-gen-skill/1.0"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / LOCAL_CONFIG_NAME


def load_local_config() -> tuple[dict[str, Any], Path]:
    path = config_path()
    if not path.exists():
        return {}, path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid local config JSON at {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"local config must be a JSON object: {path}")
    return data, path


def persist_api_key(config: dict[str, Any], path: Path, api_key: str) -> None:
    """Atomically persist a user-supplied key without ever printing it."""
    updated = dict(config)
    updated["base_url"] = str(updated.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    updated["api_key"] = api_key
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate images with the EveryGPT OpenAI-compatible API.",
    )
    parser.add_argument("prompt", nargs="?", help="Image prompt or edit instruction.")
    parser.add_argument("--list-models", action="store_true", help="List image models from /models.")
    parser.add_argument("--list-sizes", metavar="MODEL", help="List supported aspect ratios and pixel sizes for a model.")
    parser.add_argument("--image", "-i", action="append", default=[], help="Reference image path; repeat as needed.")
    parser.add_argument(
        "--output-dir",
        "-o",
        default=str(Path(tempfile.gettempdir()) / "everygpt-image-gen"),
        help="Directory for saved images. Defaults to the system temporary directory.",
    )
    parser.add_argument(
        "--api-key",
        help="Persist this API key to references/local_config.json before the request.",
    )
    parser.add_argument("--base-url", help=f"Override the configured API base URL ({DEFAULT_BASE_URL}).")
    parser.add_argument("--model", help="Image model ID. Required for generation.")
    parser.add_argument("--size", help="Explicit pixel size, for example 3840x2160.")
    parser.add_argument("--aspect-ratio", choices=ASPECT_RATIOS, help="Aspect ratio; maps to an exact size for known models.")
    parser.add_argument("--quality", help="Quality value when supported by the selected model.")
    parser.add_argument(
        "--response-format",
        choices=("url", "b64_json"),
        default="url",
        help="Preferred response format; defaults to url to avoid large Base64 responses.",
    )
    parser.add_argument("--n", type=int, default=1, help="Number of images to request.")
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--origin-ip",
        help="Connect directly to the configured API hostname at this IP, bypassing Cloudflare for long image requests.",
    )
    return parser.parse_args()


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def is_direct_origin_request(request: urllib.request.Request, origin_ip: str) -> bool:
    if not origin_ip:
        return False
    hostname = urllib.parse.urlparse(request.full_url).hostname
    base_hostname = urllib.parse.urlparse(DEFAULT_BASE_URL).hostname
    return bool(hostname and base_hostname and hostname.lower() == base_hostname.lower())


def open_request(request: urllib.request.Request, timeout: int, origin_ip: str = ""):
    """Open an API request while optionally bypassing the CDN at the DNS layer."""
    if not is_direct_origin_request(request, origin_ip):
        return urllib.request.urlopen(request, timeout=timeout)

    try:
        ipaddress.ip_address(origin_ip)
    except ValueError:
        fail(f"invalid origin IP address: {origin_ip}")

    hostname = urllib.parse.urlparse(request.full_url).hostname
    original_getaddrinfo = socket.getaddrinfo

    def resolve_origin(host: str, port: int, family: int = 0, type: int = 0,
                       proto: int = 0, flags: int = 0):
        if hostname and host.lower() == hostname.lower():
            return original_getaddrinfo(origin_ip, port, family, type, proto, flags)
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = resolve_origin
    try:
        # Keep the HTTPS URL so its SNI and Host header match the certificate;
        # bypass local HTTP proxies because they would put Cloudflare back in
        # the request path.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def request_json(request: urllib.request.Request, timeout: int, origin_ip: str = "") -> Any:
    try:
        with open_request(request, timeout, origin_ip) as response:
            text = response.read().decode("utf-8")
    except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError, TimeoutError) as exc:
        fail(
            "request connection closed before the JSON response arrived "
            f"({exc.__class__.__name__}). The generation may already be complete and billed; "
            "do not retry automatically. Check the EveryGPT log by request time before retrying."
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"request failed with HTTP {exc.code}: {body[:500]}")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError, TimeoutError)):
            fail(
                "request connection closed before the JSON response arrived. "
                "The generation may already be complete and billed; do not retry automatically. "
                "Check the EveryGPT log by request time before retrying."
            )
        fail(f"request failed: {exc.reason}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fail(f"response is not JSON: {text[:500]}")


def get_models(base_url: str, api_key: str, timeout: int, origin_ip: str = "") -> list[dict[str, Any]]:
    request = urllib.request.Request(
        api_url(base_url, "/models"),
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
    )
    payload = request_json(request, timeout, origin_ip)
    if isinstance(payload, dict):
        items = payload.get("data", payload.get("models", []))
    else:
        items = payload
    if not isinstance(items, list):
        fail("model response has no model list")
    models: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            models.append({"id": item})
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item)
    return models


def print_image_models(models: list[dict[str, Any]]) -> None:
    available = [model for model in models if model.get("id") in MODEL_SIZES]
    if not available:
        fail("/models returned no supported EveryGPT image models")
    for model in available:
        print(f"{model['id']}\taspect_ratios={','.join(ASPECT_RATIOS)}")


def print_size_options(model: str) -> None:
    sizes = MODEL_SIZES.get(model)
    if not sizes:
        fail(f"no built-in size mapping for {model}; provide --size explicitly")
    for aspect_ratio in ASPECT_RATIOS:
        print(f"{aspect_ratio}\t{sizes[aspect_ratio]}")


def resolve_size(args: argparse.Namespace) -> str:
    if args.size:
        return args.size
    model_sizes = MODEL_SIZES.get(args.model)
    if not model_sizes:
        fail("--size is required for an unrecognized model")
    if not args.aspect_ratio:
        choices = ", ".join(ASPECT_RATIOS)
        fail(f"choose --aspect-ratio ({choices}) or provide --size; use --list-sizes {args.model}")
    return model_sizes[args.aspect_ratio]


def optional_fields(args: argparse.Namespace, size: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"model": args.model, "prompt": args.prompt, "n": args.n, "size": size}
    for key in ("aspect_ratio", "quality", "response_format"):
        value = getattr(args, key)
        if value not in (None, ""):
            fields[key] = value
    return fields


def encode_multipart(fields: dict[str, Any], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----everygpt-image-gen-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add(text: str) -> None:
        chunks.append(text.encode("utf-8"))

    for name, value in fields.items():
        add(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
    for field_name, path in files:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        add(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n")
        chunks.append(path.read_bytes())
        add("\r\n")
    add(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post(url: str, api_key: str, data: bytes, content_type: str, timeout: int, origin_ip: str = "") -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "User-Agent": USER_AGENT,
        },
    )
    payload = request_json(request, timeout, origin_ip)
    if not isinstance(payload, dict):
        fail("response JSON is not an object")
    return payload


def safe_stem(prompt: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", prompt).strip(" ._")
    return (re.sub(r"\s+", "_", stem)[:40] or "image").strip("_")


def decode_base64_image(value: str) -> tuple[bytes, str]:
    match = re.match(r"^data:image/([a-zA-Z0-9.+-]+);base64,", value)
    extension = f".{match.group(1).lower().replace('jpeg', 'jpg')}" if match else ".png"
    return base64.b64decode(re.sub(r"^data:[^;]+;base64,", "", value)), extension


def download_url(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        fail(f"could not download generated image: {exc.reason}")


def save_images(payload: dict[str, Any], prompt: str, output_dir: Path, timeout: int) -> list[Path]:
    data = payload.get("data", payload.get("images"))
    items = [data] if isinstance(data, dict) else data
    if not isinstance(items, list):
        fail("response has no image data array")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp, stem, saved = time.strftime("%Y%m%d-%H%M%S"), safe_stem(prompt), []
    for index, item in enumerate(items, start=1):
        item = {"url": item} if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        suffix = f"_{index}" if len(items) > 1 else ""
        if item.get("b64_json"):
            image_bytes, extension = decode_base64_image(str(item["b64_json"]))
        elif item.get("url") or item.get("image_url"):
            url = str(item.get("url") or item["image_url"])
            image_bytes = download_url(url, timeout)
            suffix_from_url = Path(urllib.parse.urlparse(url).path).suffix.lower()
            extension = suffix_from_url if suffix_from_url in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else ".png"
        else:
            continue
        destination = output_dir / f"{timestamp}_{stem}{suffix}{extension}"
        destination.write_bytes(image_bytes)
        saved.append(destination.resolve())
    if not saved:
        fail("response has no supported image payload")
    return saved


def main() -> None:
    args = parse_args()
    if args.list_sizes:
        print_size_options(args.list_sizes)
        return
    config, path = load_local_config()
    if args.api_key:
        persist_api_key(config, path, args.api_key)
        config["api_key"] = args.api_key
    api_key = str(config.get("api_key") or "").strip()
    base_url = str(args.base_url or config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    origin_ip = str(
        args.origin_ip or config.get("origin_ip") or os.environ.get("EVERYGPT_ORIGIN_IP") or ""
    ).strip()
    if not api_key:
        fail("API key is not configured. Ask the user for a key and store it in references/local_config.json.")
    if args.list_models:
        print_image_models(get_models(base_url, api_key, args.timeout, origin_ip))
        return
    if not args.prompt:
        fail("prompt is required unless --list-models is used")
    if not args.model:
        fail("model is required. Run --list-models and ask the user to choose one.")
    if args.n < 1:
        fail("--n must be at least 1")
    size = resolve_size(args)
    image_paths = [Path(value).expanduser().resolve() for value in args.image]
    missing = [str(path) for path in image_paths if not path.is_file()]
    if missing:
        fail(f"missing reference image(s): {', '.join(missing)}")
    fields = optional_fields(args, size)
    if image_paths:
        body, content_type = encode_multipart(fields, [("image", path) for path in image_paths])
        payload = post(api_url(base_url, "/images/edits"), api_key, body, content_type, args.timeout, origin_ip)
    else:
        body = json.dumps(fields, ensure_ascii=False).encode("utf-8")
        payload = post(api_url(base_url, "/images/generations"), api_key, body, "application/json", args.timeout, origin_ip)
    for saved_path in save_images(payload, args.prompt, Path(args.output_dir).expanduser(), args.timeout):
        print(saved_path)


if __name__ == "__main__":
    main()
