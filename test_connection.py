#!/usr/bin/env python3
"""Test API key and model connectivity for olla."""

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install dependencies with: pip install -e .")
    sys.exit(1)

# Ensure 'src' is in path when running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from olla.config import find_config_path, load_config
from olla.providers import ProviderError, get_provider


def mask_key(key: str | None) -> str:
    """Mask sensitive API key for safe terminal display."""
    if not key:
        return "(none)"
    if len(key) <= 10:
        return key[:2] + "..." + key[-2:]
    return key[:8] + "..." + key[-4:]


def check_openrouter_auth(api_key: str, base_url: str) -> dict:
    """Check OpenRouter API key authentication and quota."""
    url = f"{base_url.rstrip('/')}/auth/key"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/olla/olla",
        "X-Title": "olla Connection Test",
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            return {"ok": True, "data": resp.json().get("data", {})}
        return {"ok": False, "status_code": resp.status_code, "text": resp.text}


def check_openai_auth(api_key: str, base_url: str) -> dict:
    """Check OpenAI API key authentication against /models."""
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            return {"ok": True}
        return {"ok": False, "status_code": resp.status_code, "text": resp.text}


def check_ollama_status(base_url: str = "http://localhost:11434") -> dict:
    """Check if local Ollama daemon is reachable."""
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                return {"ok": True, "models": models}
            return {"ok": False, "status_code": resp.status_code}
    except (httpx.RequestError, OSError) as e:
        return {"ok": False, "error": str(e)}


def test_model_generation(model: str, api_key: str | None = None, base_url: str | None = None) -> dict:
    """Perform a minimal test generation using olla's provider layer."""
    start_time = time.time()
    try:
        provider, _ = get_provider(model=model, api_key=api_key, base_url=base_url)
    except ProviderError as e:
        return {"ok": False, "error": f"Provider initialization failed: {e}"}

    prompt_messages = [
        {"role": "user", "content": "Ping test. Respond with the single word: PONG"}
    ]

    try:
        response_text = provider.chat(prompt_messages, think=False)
        elapsed = time.time() - start_time
        return {"ok": True, "response": response_text.strip(), "elapsed": elapsed}
    except (ProviderError, httpx.HTTPError, OSError) as e:
        elapsed = time.time() - start_time
        return {"ok": False, "error": str(e), "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Test API key connections and model availability for olla.")
    parser.add_argument("--model", default=None, help="Model to test (defaults to default_model from config)")
    parser.add_argument("--api-key", default=None, help="Explicit API key override")
    parser.add_argument("--base-url", default=None, help="Explicit base URL override")
    args = parser.parse_args()

    print("=" * 60)
    print("olla Connection & API Key Diagnostic")
    print("=" * 60)

    # 1. Config Discovery
    config_path = find_config_path()
    cfg = load_config()
    if config_path:
        print(f"[CONFIG] Found configuration: {config_path}")
    else:
        print("[CONFIG] No config file found (searched ~/.config/olla/config.toml, ~/.olla/config.toml)")

    default_model = args.model or cfg.get("default_model") or cfg.get("model")
    print(f"[CONFIG] Target model: {default_model or '(none specified)'}")

    or_cfg = cfg.get("openrouter") if isinstance(cfg.get("openrouter"), dict) else {}
    or_key = args.api_key or os.environ.get("OPENROUTER_API_KEY") or or_cfg.get("api_key") or cfg.get("openrouter_api_key") or cfg.get("api_key")
    or_base_url = args.base_url or os.environ.get("OPENROUTER_BASE_URL") or or_cfg.get("base_url") or "https://openrouter.ai/api/v1"

    oa_cfg = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}
    oa_key = args.api_key or os.environ.get("OPENAI_API_KEY") or oa_cfg.get("api_key") or cfg.get("openai_api_key") or cfg.get("api_key")
    oa_base_url = args.base_url or os.environ.get("OPENAI_BASE_URL") or oa_cfg.get("base_url") or "https://api.openai.com/v1"

    print("-" * 60)

    # 2. Check OpenRouter Connection
    if or_key:
        print(f"\n[OpenRouter] Key detected: {mask_key(or_key)}")
        print(f"[OpenRouter] Base URL: {or_base_url}")
        print("[OpenRouter] Testing key authentication...", end=" ", flush=True)
        auth_res = check_openrouter_auth(or_key, or_base_url)
        if auth_res["ok"]:
            data = auth_res.get("data", {})
            tier = "Free Tier" if data.get("is_free_tier") else "Paid Tier"
            usage = data.get("usage", 0)
            limit = data.get("limit")
            limit_str = f"{limit} USD" if limit is not None else "Unlimited"
            print("OK")
            print(f"            Status: Valid ({tier})")
            print(f"            Usage: {usage} | Credit Limit: {limit_str}")
        else:
            print("FAILED")
            print(f"            HTTP status: {auth_res.get('status_code')}")
            print(f"            Details: {auth_res.get('text')}")
    else:
        print("\n[OpenRouter] No API key detected (Set OPENROUTER_API_KEY or configure [openrouter] in config.toml)")

    # 3. Check OpenAI Connection
    if oa_key:
        print(f"\n[OpenAI] Key detected: {mask_key(oa_key)}")
        print(f"[OpenAI] Base URL: {oa_base_url}")
        print("[OpenAI] Testing key authentication...", end=" ", flush=True)
        oa_res = check_openai_auth(oa_key, oa_base_url)
        if oa_res["ok"]:
            print("OK")
            print("        Status: Valid")
        else:
            print("FAILED")
            print(f"        HTTP status: {oa_res.get('status_code')}")
            print(f"        Details: {oa_res.get('text')}")
    else:
        print("\n[OpenAI] No API key detected (Set OPENAI_API_KEY or configure [openai] in config.toml)")

    # 4. Check Local Ollama
    print("\n[Ollama] Checking local daemon (http://localhost:11434)...", end=" ", flush=True)
    ollama_res = check_ollama_status()
    if ollama_res["ok"]:
        models = ollama_res.get("models", [])
        print("OK (Connected)")
        print(f"         Local models available: {', '.join(models) if models else '(none pulled yet)'}")
    else:
        print("NOT RUNNING / NOT REACHABLE")

    # 5. Live Test Generation with Target Model
    if default_model:
        print("-" * 60)
        print(f"\n[Generation Test] Testing model '{default_model}' with sample prompt...", flush=True)
        gen_res = test_model_generation(default_model, api_key=args.api_key, base_url=args.base_url)
        if gen_res["ok"]:
            print(f"[Generation Test] SUCCESS ({gen_res['elapsed']:.2f}s)")
            print(f"                  Response: {gen_res['response']}")
        else:
            print(f"[Generation Test] FAILED ({gen_res.get('elapsed', 0.0):.2f}s)")
            print(f"                  Error: {gen_res['error']}")
    else:
        print("\n[Generation Test] Skipped (No model specified and no default_model in config.toml)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
