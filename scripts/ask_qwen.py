#!/usr/bin/env python3
"""
ask_llama.py

Minimal reproducible experiment for querying a local llama-server.

This script:
  1. Prompts the user for a query.
  2. Sends the query to llama-server using /v1/chat/completions.
  3. Prints the LLM response.

Uses only the Python standard library.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:51970")
DEFAULT_MODEL = os.environ.get("LLAMA_MODEL", "local-model")
CHAT_ENDPOINT = "/v1/chat/completions"


def build_messages(query: str):
    """
    Build the chat message payload.

    For the MRE, we keep this extremely simple:
      - one system message
      - one user message
    """
    return [
        {
            "role": "system",
            "content": "You are a concise technical assistant.",
        },
        {
            "role": "user",
            "content": query,
        },
    ]


def post_json(url: str, payload: dict, timeout: float, api_key: str | None = None):
    """
    POST a JSON payload to the given URL and return the decoded JSON response.
    """
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc

    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM server returned non-JSON response: {exc}") from exc


def query_llm(
    base_url: str,
    query: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    api_key: str | None = None,
):
    """
    Send a chat completion request to llama-server.
    """
    url = base_url.rstrip("/") + CHAT_ENDPOINT

    payload = {
        "model": model,
        "messages": build_messages(query),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    return post_json(url, payload, timeout, api_key)


def extract_content(response: dict) -> str:
    """
    Extract the assistant message from an OpenAI-compatible chat completion response.

    If the response shape is unexpected, pretty-print the whole JSON object.
    """
    try:
        return response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return json.dumps(response, indent=2)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Minimal command-line client for a local llama-server."
    )

    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Base URL of llama-server, e.g. http://127.0.0.1:8080",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model name. Often ignored by llama-server, but included for API compatibility.",
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature. Lower is more deterministic.",
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Maximum number of tokens to generate.",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=240.0,
        help="HTTP timeout in seconds.",
    )

    parser.add_argument(
        "--api-key",
        default=os.environ.get("LLAMA_API_KEY"),
        help="Optional API key if your llama-server requires one.",
    )

    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the full JSON response instead of only the assistant message.",
    )

    parser.add_argument(
        "query",
        nargs="*",
        help="Optional query text. If omitted, the script will prompt you.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.query:
        query = " ".join(args.query).strip()
    else:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            sys.exit(130)

    if not query:
        print("Empty query; refusing to call LLM.", file=sys.stderr)
        sys.exit(1)

    try:
        response = query_llm(
            base_url=args.url,
            query=query,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            api_key=args.api_key,
        )

    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted while waiting for LLM response.", file=sys.stderr)
        sys.exit(130)

    if args.raw:
        print(json.dumps(response, indent=2))
    else:
        print(extract_content(response))


if __name__ == "__main__":
    main()