#!/usr/bin/env python3
"""Minimal logprob capability probe for HermesGraph verifier candidates.

Uses only the Python standard library. It intentionally emits one short score
label so you can inspect whether the provider returns token log probabilities
before integrating it into Hermes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROMPT = """You are a narrow verifier. Judge only the criterion below.

Criterion: The candidate must contain the exact string 'VERIFIED'.
Candidate: This artifact is VERIFIED.

Return exactly one token: PASS or FAIL.
"""


def post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def cloudflare() -> dict:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    model = os.environ.get("CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash")
    if not account_id or not token:
        raise RuntimeError("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
    return post_json(
        url,
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0,
            "max_completion_tokens": 2,
            "logprobs": True,
            "top_logprobs": 5,
        },
    )


def openrouter() -> dict:
    token = os.environ.get("OPENROUTER_API_KEY")
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")
    if not token:
        raise RuntimeError("Set OPENROUTER_API_KEY")

    return post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/PetuchoDeveloper/HermesGraph",
            "X-Title": "HermesGraph verifier probe",
        },
        {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0,
            "max_tokens": 2,
            "logprobs": True,
            "top_logprobs": 5,
            "provider": {"require_parameters": True},
        },
    )


def summarize(response: dict) -> None:
    print(json.dumps(response, indent=2))
    try:
        choice = response["choices"][0]
        content = choice.get("message", {}).get("content")
        logprobs = choice.get("logprobs")
    except (KeyError, IndexError, TypeError):
        print("\nCould not find an OpenAI-compatible choices[0] response.", file=sys.stderr)
        return

    print("\n--- probe summary ---")
    print(f"completion: {content!r}")
    print(f"logprobs returned: {bool(logprobs)}")
    if not logprobs:
        print("Provider/model did not return usable logprobs. Do not enable it as a LAV verifier.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("cloudflare", "openrouter"), required=True)
    args = parser.parse_args()

    try:
        response = cloudflare() if args.provider == "cloudflare" else openrouter()
        summarize(response)
        return 0
    except Exception as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
