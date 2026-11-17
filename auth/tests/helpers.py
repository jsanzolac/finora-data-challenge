import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ev(route: str, body=None, cookie: str | None = None, path_params=None, query=None, ip="203.0.113.9"):
    method, path = route.split(" ", 1)
    e = {"routeKey": route, "headers": {"x-forwarded-for": ip},
         "requestContext": {"http": {"method": method, "path": path, "sourceIp": "198.51.100.1"}},
         "body": json.dumps(body) if body is not None else None,
         "pathParameters": path_params or {}, "queryStringParameters": query or {}}
    if cookie:
        e["cookies"] = [f"dq_session={cookie}"]
    return e


def body_of(r):
    return json.loads(r["body"])


def token_of(r):
    for c in r.get("cookies", []):
        if c.startswith("dq_session=") and not c.startswith("dq_session=;"):
            return c.split(";")[0].split("=", 1)[1]
    return None


def load_auth():
    import importlib.util
    spec = importlib.util.spec_from_file_location("auth_handler", ROOT / "auth" / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
