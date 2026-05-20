from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import time


MEDIAMTX_API_BASE = os.getenv("MEDIAMTX_API_BASE", "http://localhost:9997").rstrip("/")
PUBLIC_WEBRTC_BASE = os.getenv("PUBLIC_WEBRTC_BASE", "http://localhost:8889").rstrip("/")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))

PATH_NAME_RE = re.compile(r"^[A-Za-z0-9_.~-]{1,80}$")


class ApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def request_json(method, path, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(f"{MEDIAMTX_API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        raise ApiError(exc.code, payload.get("error") or f"MediaMTX API returned {exc.code}") from exc
    except URLError as exc:
        raise ApiError(502, f"Cannot reach MediaMTX API: {exc.reason}") from exc


def validate_rtsp_url(rtsp_url):
    parsed = urlparse(rtsp_url)
    if parsed.scheme not in ("rtsp", "rtsps") or not parsed.netloc:
        raise ApiError(400, "rtspUrl must be a valid rtsp:// or rtsps:// URL")


def normalize_path_name(name, rtsp_url):
    if not name:
        digest = hashlib.sha1(f"{rtsp_url}:{time.time_ns()}".encode("utf-8")).hexdigest()[:10]
        return f"stream-{digest}"
    if not PATH_NAME_RE.match(name):
        raise ApiError(400, "name can only contain letters, numbers, '_', '.', '~' or '-', max length 80")
    return name


def stream_payload(name, rtsp_url, source_on_demand, rtsp_transport):
    encoded_name = quote(name, safe="")
    return {
        "name": name,
        "rtspUrl": rtsp_url,
        "webrtcUrl": f"{PUBLIC_WEBRTC_BASE}/{encoded_name}",
        "whepUrl": f"{PUBLIC_WEBRTC_BASE}/{encoded_name}/whep",
        "statusUrl": f"/api/streams/{encoded_name}",
        "sourceOnDemand": source_on_demand,
        "rtspTransport": rtsp_transport,
    }


def upsert_stream(payload):
    rtsp_url = payload.get("rtspUrl")
    if not isinstance(rtsp_url, str):
        raise ApiError(400, "rtspUrl is required")
    validate_rtsp_url(rtsp_url)

    name = normalize_path_name(payload.get("name"), rtsp_url)
    source_on_demand = bool(payload.get("sourceOnDemand", True))
    rtsp_transport = payload.get("rtspTransport", "tcp")
    if rtsp_transport not in ("tcp", "udp", "multicast", "automatic"):
        raise ApiError(400, "rtspTransport must be one of tcp, udp, multicast, automatic")

    config = {
        "source": rtsp_url,
        "sourceOnDemand": source_on_demand,
        "rtspTransport": rtsp_transport,
    }

    encoded_name = quote(name, safe="")
    try:
        request_json("GET", f"/v3/config/paths/get/{encoded_name}")
        request_json("PATCH", f"/v3/config/paths/patch/{encoded_name}", config)
    except ApiError as exc:
        if exc.status_code != 404:
            raise
        request_json("POST", f"/v3/config/paths/add/{encoded_name}", config)

    return stream_payload(name, rtsp_url, source_on_demand, rtsp_transport)


def get_stream(name):
    if not PATH_NAME_RE.match(name):
        raise ApiError(400, "invalid stream name")
    encoded_name = quote(name, safe="")
    conf = request_json("GET", f"/v3/config/paths/get/{encoded_name}")
    state = None
    try:
        state = request_json("GET", f"/v3/paths/get/{encoded_name}")
    except ApiError as exc:
        if exc.status_code != 404:
            raise

    response = stream_payload(
        name,
        conf.get("source", ""),
        bool(conf.get("sourceOnDemand", False)),
        conf.get("rtspTransport", "automatic"),
    )
    response["online"] = bool(state and state.get("online"))
    response["tracks"] = state.get("tracks2", []) if state else []
    return response


def delete_stream(name):
    if not PATH_NAME_RE.match(name):
        raise ApiError(400, "invalid stream name")
    request_json("DELETE", f"/v3/config/paths/delete/{quote(name, safe='')}")
    return {"deleted": True, "name": name}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_DELETE(self):
        self.handle_request()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def handle_request(self):
        try:
            if self.path == "/health" and self.command == "GET":
                info = request_json("GET", "/v3/info")
                self.send_json(200, {"ok": True, "mediamtx": info})
                return

            if self.path == "/api/streams" and self.command == "POST":
                self.send_json(201, upsert_stream(self.read_body()))
                return

            match = re.match(r"^/api/streams/([A-Za-z0-9_.~-]+)$", self.path)
            if match and self.command == "GET":
                self.send_json(200, get_stream(match.group(1)))
                return

            if match and self.command == "DELETE":
                self.send_json(200, delete_stream(match.group(1)))
                return

            self.send_json(404, {"error": "not found"})
        except ApiError as exc:
            self.send_json(exc.status_code, {"error": exc.message})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "request body must be valid JSON"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = ThreadingHTTPServer((API_HOST, API_PORT), Handler)
    print(f"RTSP -> WebRTC API listening on http://{API_HOST}:{API_PORT}")
    print(f"Using MediaMTX API at {MEDIAMTX_API_BASE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
