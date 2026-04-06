from collections.abc import Iterable


def emit_progress(writer, step: str, status: str, detail: str | None = None) -> None:
    payload = {"type": "progress", "step": step, "status": status}
    if detail:
        payload["detail"] = detail
    writer(payload)


def preview_list(values: Iterable[object], limit: int = 6) -> str:
    items = [str(value) for value in values if str(value).strip()]
    if not items:
        return "无"
    if len(items) <= limit:
        return "、".join(items)
    return f"{'、'.join(items[:limit])} 等 {len(items)} 项"


def preview_text(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."
