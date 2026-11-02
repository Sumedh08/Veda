from datetime import UTC, datetime, timedelta

from app.models import Project, ResearchJob


def test_permanent_project_purge_waits_for_live_research_lease(client):
    project = client.post(
        "/api/v1/projects",
        json={"title": "Lease guarded purge", "domain": "testing"},
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Should an active job prevent permanent project deletion?",
            "idempotency_key": "lease-guard-purge-01",
        },
    ).json()
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204

    now = datetime.now(UTC)
    with client.db_sessions() as db:
        stored_job = db.get(ResearchJob, job["id"])
        assert stored_job is not None
        stored_job.status = "active"
        stored_job.lease_owner = "fixture-active-worker"
        stored_job.lease_expires_at = now + timedelta(minutes=2)
        db.commit()

    deletion_path = f"/api/v1/projects/{project['id']}/permanent"
    payload = {"confirmation": "DELETE", "project_title": project["title"]}
    blocked = client.request("DELETE", deletion_path, json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == (
        "A research step is still running. Wait for it to save or finish before deleting this project."
    )
    with client.db_sessions() as db:
        assert db.get(Project, project["id"]) is not None
        retained_job = db.get(ResearchJob, job["id"])
        assert retained_job is not None
        assert retained_job.lease_owner == "fixture-active-worker"

    with client.db_sessions() as db:
        expired_job = db.get(ResearchJob, job["id"])
        assert expired_job is not None
        expired_job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    deleted = client.request("DELETE", deletion_path, json=payload)
    assert deleted.status_code == 204
    with client.db_sessions() as db:
        assert db.get(Project, project["id"]) is None
        assert db.get(ResearchJob, job["id"]) is None
