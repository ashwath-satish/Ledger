"""
Featherless relay for LEDGER.

Browsers block cross-origin calls from a file:// page, so during the demo we
bounce inference through localhost. This adds nothing but CORS headers.

    pip install flask requests
    python proxy.py

Then set the endpoint in LEDGER's inference settings to:
    http://localhost:8787/v1/chat/completions
"""
from flask import Flask, request, Response
import requests

UPSTREAM = "https://api.featherless.ai/v1/chat/completions"

app = Flask(__name__)


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
def relay():
    if request.method == "OPTIONS":
        return Response(status=204)

    upstream = requests.post(
        UPSTREAM,
        headers={
            "Content-Type": "application/json",
            "Authorization": request.headers.get("Authorization", ""),
        },
        json=request.get_json(),
        timeout=120,
    )
    return Response(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "application/json"),
    )


if __name__ == "__main__":
    print("LEDGER relay on http://localhost:8787  →  " + UPSTREAM)
    app.run(port=8787)
