from support import add_test_passage

from app.models import Claim, ResearchJob, Source
from app.research import workflow
from app.schemas import build_report_stage_result


def _project(client):
    response = client.post(
        "/api/v1/projects", json={"title": "Follow-up study", "domain": "AI economics"}
    )
    assert response.status_code == 201
    return response.json()


def _create_job(client, project_id, **extra):
    payload = {
        "question": "How do AI tools change productivity for customer support workers?",
        "idempotency_key": extra.pop("idempotency_key", "conversation-job-0001"),
        **extra,
    }
    response = client.post(f"/api/v1/projects/{project_id}/research-jobs", json=payload)
    assert response.status_code == 201, response.text
    return response.json(), payload


def _add_parent_evidence(client, parent_job_id):
    with client.db_sessions() as db:
        source = Source(
            job_id=parent_job_id,
            external_id="fixture:parent-productivity",
            title="Productivity among support workers",
            retrieval_status="abstract_only",
        )
        other_source = Source(
            job_id=parent_job_id,
            external_id="fixture:parent-unrelated",
            title="A different topic",
            retrieval_status="abstract_only",
        )
        db.add_all([source, other_source])
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=1,
            locator="abstract, paragraph 1",
            content="The AI tools improved productivity for customer support workers.",
        )
        other_passage = add_test_passage(
            db,
            other_source,
            ordinal=1,
            locator="abstract, paragraph 1",
            content="This study describes unrelated coastal erosion measurements.",
        )
        db.flush()
        relevant = Claim(
            job_id=parent_job_id,
            source_id=source.id,
            passage_id=passage.id,
            text=passage.content,
        )
        unrelated = Claim(
            job_id=parent_job_id,
            source_id=other_source.id,
            passage_id=other_passage.id,
            text=other_passage.content,
        )
        db.add_all([relevant, unrelated])
        db.commit()
        return relevant.id, unrelated.id


def test_job_creation_starts_persistent_conversation_and_is_idempotent(client):
    project = _project(client)
    job, payload = _create_job(client, project["id"])

    assert job["conversation_id"]
    messages = client.get(f"/api/v1/conversations/{job['conversation_id']}/messages").json()[
        "items"
    ]
    assert [
        (message["role"], message["content"], message["related_job_id"]) for message in messages
    ] == [("user", job["question"], job["id"])]

    repeated = client.post(f"/api/v1/projects/{project['id']}/research-jobs", json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == job["id"]
    assert (
        len(client.get(f"/api/v1/conversations/{job['conversation_id']}/messages").json()["items"])
        == 1
    )


def test_follow_up_reuses_only_relevant_parent_claim_ids_with_provenance(client):
    project = _project(client)
    parent, _ = _create_job(client, project["id"])
    relevant_id, unrelated_id = _add_parent_evidence(client, parent["id"])

    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What new studies measure productivity for customer support workers?",
            "idempotency_key": "conversation-followup-0001",
            "parent_job_id": parent["id"],
        },
    )
    assert response.status_code == 201, response.text
    child = response.json()
    assert child["parent_job_id"] == parent["id"]
    assert child["conversation_id"] == parent["conversation_id"]

    messages = client.get(f"/api/v1/conversations/{child['conversation_id']}/messages").json()[
        "items"
    ]
    assert [message["related_job_id"] for message in messages] == [parent["id"], child["id"]]

    context = client.get(f"/api/v1/research-jobs/{child['id']}/follow-up-context")
    assert context.status_code == 200
    assert context.json()["status"] == "context_attached"
    assert [item["claim"]["id"] for item in context.json()["claims"]] == [relevant_id]
    item = context.json()["claims"][0]
    assert item["source"]["title"] == "Productivity among support workers"
    assert item["passage"]["locator"] == "abstract, paragraph 1"
    assert unrelated_id not in {entry["claim"]["id"] for entry in context.json()["claims"]}
    assert "not copied into this run's claims or citations" in context.json()["reuse_boundary"]

    plan_step = client.post(
        f"/api/v1/research-jobs/{child['id']}/advance",
        json={"operation_key": "conversation-followup-plan-01"},
    )
    assert plan_step.status_code == 200
    plan = client.get(f"/api/v1/research-jobs/{child['id']}/plan").json()
    assert any("newly retrieved evidence" in item["text"] for item in plan["subquestions"])
    assert any("Parent claims are context" in item["purpose"] for item in plan["subquestions"])
    assert client.get(f"/api/v1/research-jobs/{child['id']}/claims").json()["items"] == []

    client.test_user["id"] = "20000000-0000-4000-8000-000000000002"
    assert client.get(f"/api/v1/research-jobs/{child['id']}/follow-up-context").status_code == 404


def test_conversation_rejects_blank_messages_and_cross_project_related_jobs(client):
    project = _project(client)
    first, _ = _create_job(client, project["id"])
    second_project = _project(client)
    second, _ = _create_job(client, second_project["id"], idempotency_key="conversation-job-0002")

    blank = client.post(
        f"/api/v1/conversations/{first['conversation_id']}/messages",
        json={"content": "   "},
    )
    assert blank.status_code == 422
    cross_project = client.post(
        f"/api/v1/conversations/{first['conversation_id']}/messages",
        json={"content": "This should not link across projects.", "related_job_id": second["id"]},
    )
    assert cross_project.status_code == 422
    paged = client.get(
        f"/api/v1/conversations/{first['conversation_id']}/messages?limit=1&offset=0"
    )
    assert paged.status_code == 200
    assert paged.json()["limit"] == 1
    assert len(paged.json()["items"]) == 1


def test_conversations_and_messages_are_bounded_and_paginated(client):
    project = _project(client)
    parent, _ = _create_job(client, project["id"])
    child_response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What is newly known about worker productivity after AI adoption?",
            "idempotency_key": "conversation-pagination-child",
            "parent_job_id": parent["id"],
        },
    )
    assert child_response.status_code == 201
    child = child_response.json()

    newest = client.get(
        f"/api/v1/conversations/{parent['conversation_id']}/messages?limit=1&offset=0"
    ).json()
    older = client.get(
        f"/api/v1/conversations/{parent['conversation_id']}/messages?limit=1&offset=1"
    ).json()
    assert newest["has_more"] is True
    assert newest["total"] == 2
    assert older["has_more"] is False
    assert older["total"] == 2
    assert newest["items"][0]["related_job_id"] == child["id"]
    assert older["items"][0]["related_job_id"] == parent["id"]

    client.post(f"/api/v1/projects/{project['id']}/conversations")
    first_page = client.get(
        f"/api/v1/projects/{project['id']}/conversations?limit=1&offset=0"
    ).json()
    second_page = client.get(
        f"/api/v1/projects/{project['id']}/conversations?limit=1&offset=1"
    ).json()
    assert first_page["limit"] == second_page["limit"] == 1
    assert len(first_page["items"]) == len(second_page["items"]) == 1
    assert first_page["total"] == second_page["total"] == 2
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]


def test_report_persistence_adds_one_assistant_conversation_message(client):
    project = _project(client)
    job_data, _ = _create_job(client, project["id"])
    result = workflow.StageResult(
        message="Report saved.",
        event_data={},
        next_stage="complete",
        status="completed_with_limitations",
        report=build_report_stage_result("# Report", {}, {"status": "passed"}, None),
    )

    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_data["id"])
        workflow.persist_result(db, job, result)
        db.commit()
        workflow.persist_result(db, job, result)
        db.commit()

    messages = client.get(f"/api/v1/conversations/{job_data['conversation_id']}/messages").json()[
        "items"
    ]
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert "Open the Report tab" in assistant_messages[0]["content"]
    assert assistant_messages[0]["related_job_id"] == job_data["id"]
