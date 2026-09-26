"""Idempotently fill a running local API with automotive demo polls."""

import argparse
import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any


class ApiClient:
    def __init__(self, base_url: str, admin_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = json.dumps(body, ensure_ascii=False).encode() if body else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers or self.admin_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            details = exc.read().decode()
            raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {details}") from exc
        return json.loads(payload) if payload else None


def poll(
    name: str,
    *,
    status: str,
    show_time: datetime | None,
    duration: int,
    options: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "show_time": show_time.isoformat() if show_time else None,
        "duration_seconds": duration,
        "options": [
            {"key": f"option-{index + 1}", "label": label}
            for index, label in enumerate(options)
        ],
    }


def demo_polls(now: datetime) -> list[dict[str, Any]]:
    return [
        poll(
            "Какой тип кузова практичнее для города?",
            status="published",
            show_time=now - timedelta(minutes=1),
            duration=3600,
            options=["Седан", "Кроссовер", "Хэтчбек", "Универсал"],
        ),
        poll(
            "Автомат, механика или робот — что выбираете?",
            status="published",
            show_time=now - timedelta(minutes=1),
            duration=3600,
            options=["Автомат", "Механика", "Робот", "Вариатор"],
        ),
        poll(
            "Какой электромобиль вы бы выбрали?",
            status="published",
            show_time=now + timedelta(days=1),
            duration=120,
            options=["Tesla Model 3", "Zeekr 001", "BYD Seal", "Porsche Taycan"],
        ),
        poll(
            "Какая система безопасности важнее?",
            status="published",
            show_time=now + timedelta(hours=2),
            duration=180,
            options=[
                "ABS и ESP",
                "Контроль слепых зон",
                "Адаптивный круиз",
                "Автоторможение",
            ],
        ),
        poll(
            "Что важнее всего при выборе автомобиля?",
            status="published",
            show_time=now - timedelta(days=2),
            duration=60,
            options=["Надёжность", "Комфорт", "Динамика", "Экономичность"],
        ),
        poll(
            "Какой японский бренд самый надёжный?",
            status="published",
            show_time=now - timedelta(days=1),
            duration=120,
            options=["Toyota", "Honda", "Mazda", "Subaru"],
        ),
        poll(
            "Какую марку автомобиля вы предпочитаете?",
            status="draft",
            show_time=None,
            duration=60,
            options=["BMW", "Mercedes-Benz", "Audi", "Toyota"],
        ),
        poll(
            "Какой бюджет оптимален для первого автомобиля?",
            status="draft",
            show_time=None,
            duration=120,
            options=["До 1 млн ₽", "1–2 млн ₽", "2–3 млн ₽", "Больше 3 млн ₽"],
        ),
        poll(
            "Что должно быть в современной мультимедиа?",
            status="draft",
            show_time=None,
            duration=90,
            options=[
                "CarPlay / Android Auto",
                "Навигация",
                "Голосовой помощник",
                "Премиальная музыка",
            ],
        ),
    ]


def seed(api: ApiClient) -> None:
    existing = api.request("/questions")
    existing_names = {question["name"] for question in existing}
    created: list[dict[str, Any]] = []

    for payload in demo_polls(datetime.now(UTC)):
        if payload["name"] in existing_names:
            continue
        created.append(api.request("/questions", method="POST", body=payload))

    live_questions = [
        question for question in created if question["effective_status"] == "live"
    ]
    vote_distribution = [0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 3]
    for question in live_questions:
        for option_index in vote_distribution:
            option_key = question["options"][option_index]["key"]
            api.request(
                f"/questionnaire/{question['id']}/votes",
                method="POST",
                body={"option": option_key},
                headers={
                    "Content-Type": "application/json",
                    "Cookie": f"vid={uuid.uuid4()}",
                },
            )

    total = len(api.request("/questions"))
    print(f"Created {len(created)} demo polls; total questions: {total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--admin-token", default="dev-admin-token")
    args = parser.parse_args()
    seed(ApiClient(args.api_url, args.admin_token))


if __name__ == "__main__":
    main()
