"""Small repeatable HTTP load probe for the vote endpoint."""

import argparse
import asyncio
import statistics
import time
from uuid import uuid4

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


async def run(args: argparse.Namespace) -> None:
    queue: asyncio.Queue[int] = asyncio.Queue()
    for item in range(args.requests):
        queue.put_nowait(item)

    latencies: list[float] = []
    statuses: dict[int, int] = {}
    url = f"{args.base_url}/questionnaire/{args.question_id}/votes"

    async with httpx.AsyncClient(timeout=30) as client:
        async def worker() -> None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                started = time.perf_counter()
                response = await client.post(
                    url,
                    json={"option": args.option},
                    cookies={"vid": str(uuid4())},
                )
                latencies.append((time.perf_counter() - started) * 1000)
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
                queue.task_done()

        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
        elapsed = time.perf_counter() - started

    print(f"requests={args.requests} concurrency={args.concurrency}")
    print(f"elapsed={elapsed:.3f}s rps={args.requests / elapsed:.1f}")
    print(
        "latency_ms "
        f"mean={statistics.mean(latencies):.1f} "
        f"p50={percentile(latencies, 0.50):.1f} "
        f"p95={percentile(latencies, 0.95):.1f} "
        f"p99={percentile(latencies, 0.99):.1f}"
    )
    print(f"statuses={statuses}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question_id", type=int)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--option", default="a")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
