import os
import socket
import sys
import time


def wait_for_port(name: str, host: str, port: int, timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                print(f"[wait] {name} is ready at {host}:{port}", flush=True)
                return
        except OSError:
            time.sleep(2)
    raise TimeoutError(f"{name} was not ready within {timeout_seconds}s: {host}:{port}")


def main() -> int:
    targets = [
        ("meta mysql", os.getenv("META_DB_HOST", "mysql"), int(os.getenv("META_DB_PORT", "3306"))),
        ("dw mysql", os.getenv("DW_DB_HOST", "mysql"), int(os.getenv("DW_DB_PORT", "3306"))),
        ("qdrant", os.getenv("QDRANT_HOST", "qdrant"), int(os.getenv("QDRANT_PORT", "6333"))),
        ("elasticsearch", os.getenv("ES_HOST", "elasticsearch"), int(os.getenv("ES_PORT", "9200"))),
    ]

    embedding_host = os.getenv("EMBEDDING_HOST", "")
    if embedding_host and embedding_host != "openai":
        targets.append(
            ("embedding", embedding_host, int(os.getenv("EMBEDDING_PORT", "80"))),
        )

    try:
        for name, host, port in targets:
            wait_for_port(name, host, port)
    except TimeoutError as exc:
        print(f"[wait] {exc}", file=sys.stderr, flush=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
