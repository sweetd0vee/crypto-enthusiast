import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 against the Docker stack",
)

API_URL = os.getenv("API_URL", "http://localhost:8080")
ADMIN_HEADERS = {
    "Authorization": f"Bearer {os.getenv('ADMIN_TOKEN', 'dev-admin-token')}"
}


def question_payload(
    name: str,
    show_time: datetime | None,
    *,
    status: str = "published",
    duration_seconds: int = 60,
) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "show_time": show_time.isoformat() if show_time else None,
        "duration_seconds": duration_seconds,
        "options": [
            {"key": "yes", "label": "Да"},
            {"key": "no", "label": "Нет"},
        ],
    }


async def test_complete_anonymous_voting_scenario() -> None:
    now = datetime.now(UTC)
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as admin:
        live_response = await admin.post(
            "/questions",
            headers=ADMIN_HEADERS,
            json=question_payload(
                f"Integration live {now.isoformat()}",
                now - timedelta(seconds=1),
            ),
        )
        assert live_response.status_code == 201
        live_id = live_response.json()["id"]

        async with httpx.AsyncClient(base_url=API_URL, timeout=10) as viewer_one:
            form = await viewer_one.get(f"/questionnaire/{live_id}")
            assert form.status_code == 200
            assert "vid" in viewer_one.cookies
            assert set(form.json()) == {"id", "name", "closes_at", "options"}

            accepted = await viewer_one.post(
                f"/questionnaire/{live_id}/votes",
                json={"option": "yes"},
            )
            duplicate = await viewer_one.post(
                f"/questionnaire/{live_id}/votes",
                json={"option": "yes"},
            )
            assert accepted.status_code == 201
            assert duplicate.status_code == 409
            assert duplicate.json()["error"] == "already_voted"

        async with httpx.AsyncClient(base_url=API_URL, timeout=10) as viewer_two:
            second_vote = await viewer_two.post(
                f"/questionnaire/{live_id}/votes",
                json={"option": "no"},
            )
            assert second_vote.status_code == 201

        result = await admin.get(
            f"/questions/{live_id}/results",
            headers=ADMIN_HEADERS,
        )
        assert result.status_code == 200
        assert result.json()["total"] == 2
        assert [row["count"] for row in result.json()["counts"]] == [1, 1]

        closed_response = await admin.post(
            "/questions",
            headers=ADMIN_HEADERS,
            json=question_payload(
                f"Integration closed {now.isoformat()}",
                now - timedelta(minutes=2),
                duration_seconds=10,
            ),
        )
        assert closed_response.status_code == 201
        closed_id = closed_response.json()["id"]

        async with httpx.AsyncClient(base_url=API_URL, timeout=10) as late_viewer:
            closed_form = await late_viewer.get(f"/questionnaire/{closed_id}")
            closed_vote = await late_viewer.post(
                f"/questionnaire/{closed_id}/votes",
                json={"option": "yes"},
            )
            assert closed_form.status_code == 410
            assert closed_vote.status_code == 410
            assert closed_vote.json()["error"] == "window_closed"

        draft_response = await admin.post(
            "/questions",
            headers=ADMIN_HEADERS,
            json=question_payload(
                f"Integration draft {now.isoformat()}",
                None,
                status="draft",
            ),
        )
        assert draft_response.status_code == 201
        draft_id = draft_response.json()["id"]

        empty_result = await admin.get(
            f"/questions/{draft_id}/results",
            headers=ADMIN_HEADERS,
        )
        deleted = await admin.delete(
            f"/questions/{draft_id}",
            headers=ADMIN_HEADERS,
        )
        assert empty_result.status_code == 200
        assert empty_result.json()["total"] == 0
        assert deleted.status_code == 204
