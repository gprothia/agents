#!/usr/bin/env python3
"""Generate synthetic inference traffic through the LiteLLM gateway.

Fires randomized prompts at the gateway, rotating across every registered model
so Cloud Monitoring, the LiteLLM Admin UI, quota dashboards, and billing views
all have data spanning the three backends.

This exercises the same path a real consumer uses: one OpenAI-compatible
endpoint, a virtual key for auth, and a model name that selects the backend.
No Google credentials are required.

Auth: a LiteLLM virtual key, passed with --api-key or via LITELLM_API_KEY.

Examples:
    # 60 requests spread evenly across all three models, 5 at a time
    python generate_gemini_traffic.py --gateway http://10.10.0.3:4000 \
        --api-key sk-... --requests 60 --concurrency 5

    # Through an IAP tunnel on localhost
    python generate_gemini_traffic.py --api-key sk-... --requests 30

    # Sustained load for 10 minutes at ~2 req/s
    python generate_gemini_traffic.py --api-key sk-... --duration 600 --qps 2

    # Target a single backend
    python generate_gemini_traffic.py --api-key sk-... --models gke-gemma
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import itertools
import json
import os
import random
import signal
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

DEFAULT_GATEWAY = "http://localhost:4000"

# The three backends registered in the gateway's model_list. Each is a
# different deployment type behind an identical request shape.
DEFAULT_MODELS = [
    "serverless-gemini",   # managed Gemini on Vertex AI
    "selfhosted-gemma",    # self-deployed Gemma on a Model Garden endpoint
    "gke-gemma",           # Gemma served by vLLM on GKE
]


# Prompt fragments recombined at random so every request is unique. Unique
# prompts defeat any response caching and produce a realistic spread of
# input/output token counts.
TOPICS = [
    "supply chain resilience",
    "quantum error correction",
    "urban vertical farming",
    "the Antikythera mechanism",
    "carbon capture economics",
    "deep sea bioluminescence",
    "the Bronze Age collapse",
    "distributed consensus protocols",
    "monsoon prediction models",
    "the history of the shipping container",
    "mycorrhizal networks",
    "high frequency trading latency",
    "Roman concrete durability",
    "arctic permafrost methane",
    "the economics of desalination",
    "spacecraft thermal management",
    "coffee fermentation chemistry",
    "the Voynich manuscript",
    "grid scale battery storage",
    "medieval guild structures",
]

TASKS = [
    "Explain {topic} to a curious teenager.",
    "List three common misconceptions about {topic}.",
    "Write a short haiku about {topic}.",
    "Summarize the current state of {topic} in two sentences.",
    "What are the biggest unsolved problems in {topic}?",
    "Compare {topic} with a similar concept and highlight the differences.",
    "Give me a surprising fact about {topic} and explain why it is surprising.",
    "Draft a one-paragraph executive briefing on {topic}.",
    "What would a skeptic say about {topic}?",
    "Describe how {topic} might change over the next decade.",
]

PERSONAS = [
    "",
    " Answer as a patient university lecturer.",
    " Be blunt and use no more than 40 words.",
    " Use a bulleted list.",
    " Include one concrete real-world example.",
]

_print_lock = threading.Lock()
_stop = threading.Event()


@dataclasses.dataclass
class Result:
    index: int
    model: str
    ok: bool
    latency_s: float
    prompt_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


def build_prompt(rng: random.Random) -> str:
    """Compose a random prompt from the fragment pools."""
    topic = rng.choice(TOPICS)
    task = rng.choice(TASKS).format(topic=topic)
    persona = rng.choice(PERSONAS)
    # Trailing nonce keeps every prompt byte-unique without skewing semantics.
    nonce = rng.randint(1000, 9999)
    return f"{task}{persona} (ref #{nonce})"


def log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def send_one(gateway: str, api_key: str, model: str, index: int, seed: int,
             max_tokens: int, temperature: float, timeout: float) -> Result:
    """Issue a single chat completion against the gateway and record usage."""
    rng = random.Random(seed)
    prompt = build_prompt(rng)

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{gateway.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        elapsed = time.perf_counter() - started
        usage = body.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        choices = body.get("choices") or [{}]
        content = (choices[0].get("message", {}).get("content") or "")
        preview = content.strip().replace("\n", " ")[:56]
        log(f"[{index:>4}] ok   {model:<18} {elapsed:6.2f}s  "
            f"in={prompt_tokens:<5} out={output_tokens:<5} {preview}")
        return Result(index, model, True, elapsed, prompt_tokens, output_tokens)

    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        # The gateway returns useful JSON on 4xx/5xx - surface it rather than
        # just the status line, since that is where key/model errors appear.
        try:
            detail = exc.read().decode("utf-8", "replace")[:160]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        message = f"{exc.code} {detail}"
        log(f"[{index:>4}] FAIL {model:<18} {elapsed:6.2f}s  {message[:96]}")
        return Result(index, model, False, elapsed, error=message)

    except Exception as exc:  # noqa: BLE001 - keep the load generator alive
        elapsed = time.perf_counter() - started
        message = f"{type(exc).__name__}: {exc}"
        log(f"[{index:>4}] FAIL {model:<18} {elapsed:6.2f}s  {message[:96]}")
        return Result(index, model, False, elapsed, error=message)


def _percentiles(latencies: List[float]) -> tuple:
    ordered = sorted(latencies)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return p50, p95


def summarize(results: List[Result], wall_s: float, gateway: str) -> None:
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]

    print("\n" + "=" * 78)
    print(f"  Traffic summary - {gateway}")
    print("=" * 78)
    print(f"  Requests sent     : {len(results)}")
    print(f"  Succeeded         : {len(ok)}")
    print(f"  Failed            : {len(failed)}")
    print(f"  Wall clock        : {wall_s:.1f}s")
    if wall_s > 0:
        print(f"  Throughput        : {len(results) / wall_s:.2f} req/s")

    # Per-model breakdown is the point of routing through the gateway: it shows
    # how the three backends compare under identical prompts.
    models = sorted({r.model for r in results})
    if models:
        print("\n  Per-model breakdown:")
        header = (f"    {'model':<20}{'ok':>5}{'fail':>6}"
                  f"{'p50':>9}{'p95':>9}{'in':>9}{'out':>9}")
        print(header)
        print("    " + "-" * (len(header) - 4))
        for model in models:
            m_ok = [r for r in ok if r.model == model]
            m_fail = [r for r in failed if r.model == model]
            if m_ok:
                p50, p95 = _percentiles([r.latency_s for r in m_ok])
                p50_s, p95_s = f"{p50:.2f}s", f"{p95:.2f}s"
            else:
                p50_s = p95_s = "-"
            tok_in = sum(r.prompt_tokens for r in m_ok)
            tok_out = sum(r.output_tokens for r in m_ok)
            print(f"    {model:<20}{len(m_ok):>5}{len(m_fail):>6}"
                  f"{p50_s:>9}{p95_s:>9}{tok_in:>9,}{tok_out:>9,}")

    if ok:
        p50, p95 = _percentiles([r.latency_s for r in ok])
        print(f"\n  Overall p50 / p95 : {p50:.2f}s / {p95:.2f}s")
        print(f"  Input tokens      : {sum(r.prompt_tokens for r in ok):,}")
        print(f"  Output tokens     : {sum(r.output_tokens for r in ok):,}")

    if failed:
        print("\n  Error breakdown:")
        tally: Dict[str, int] = {}
        for r in failed:
            key = r.error.split(":")[0][:70]
            tally[key] = tally.get(key, 0) + 1
        for key, count in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>4}x  {key}")
    print("=" * 78)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate randomized traffic through the LiteLLM gateway.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--gateway", default=os.environ.get("LITELLM_GATEWAY", DEFAULT_GATEWAY),
                        help="Base URL of the LiteLLM gateway")
    parser.add_argument("--api-key", default=os.environ.get("LITELLM_API_KEY"),
                        help="LiteLLM virtual key (or set LITELLM_API_KEY)")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                        help="Model names to rotate across")
    parser.add_argument("--requests", type=int, default=24,
                        help="Total number of requests (ignored if --duration is set)")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Run for this many seconds instead of a fixed count")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Parallel in-flight requests")
    parser.add_argument("--qps", type=float, default=0.0,
                        help="Throttle to this rate; 0 means unthrottled")
    parser.add_argument("--max-tokens", type=int, default=256,
                        help="max_tokens per request")
    parser.add_argument("--temperature", type=float, default=1.0,
                        help="Sampling temperature")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="Per-request timeout in seconds")
    parser.add_argument("--seed", type=int, default=None,
                        help="Base seed for reproducible prompts")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Fail fast on a missing key rather than emitting a wall of 401s.
    if not args.api_key:
        print("error: no virtual key. Pass --api-key or set LITELLM_API_KEY.",
              file=sys.stderr)
        return 2

    def handle_sigint(_signum, _frame):
        if not _stop.is_set():
            log("\nStopping after in-flight requests finish (Ctrl-C again to force)...")
            _stop.set()
        else:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_sigint)

    mode = (f"{args.duration:.0f}s" if args.duration > 0
            else f"{args.requests} requests")
    print(f"Gateway     : {args.gateway}")
    print(f"Models      : {', '.join(args.models)}")
    print(f"Workload    : {mode}, concurrency={args.concurrency}, "
          f"qps={'unthrottled' if args.qps <= 0 else args.qps}")
    print("-" * 78)

    base_seed = args.seed if args.seed is not None else random.randrange(2**31)
    interval = 1.0 / args.qps if args.qps > 0 else 0.0
    deadline = time.time() + args.duration if args.duration > 0 else None

    results: List[Result] = []
    started = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = set()
        counter = itertools.count(1)
        next_slot = time.perf_counter()

        while not _stop.is_set():
            if deadline is not None:
                if time.time() >= deadline:
                    break
            elif len(results) + len(futures) >= args.requests:
                break

            # Keep the in-flight window bounded so memory stays flat.
            while len(futures) >= args.concurrency:
                done, futures = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED)
                results.extend(f.result() for f in done)

            if interval > 0:
                sleep_for = next_slot - time.perf_counter()
                if sleep_for > 0:
                    # Sleep in slices so Ctrl-C stays responsive.
                    _stop.wait(sleep_for)
                next_slot += interval

            index = next(counter)
            # Round-robin rather than random so every backend receives an equal
            # share, which keeps the per-model comparison fair.
            model = args.models[(index - 1) % len(args.models)]
            futures.add(pool.submit(
                send_one, args.gateway, args.api_key, model, index,
                base_seed + index, args.max_tokens, args.temperature,
                args.timeout))

        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    wall = time.perf_counter() - started
    summarize(results, wall, args.gateway)
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
