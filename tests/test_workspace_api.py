import time
from fastapi.testclient import TestClient
from workflow.service import create_workflow
from web.server import create_app


def client(tmp_path):
    return TestClient(create_app(tmp_path, lambda mode: create_workflow(mode, tmp_path)))


def wait_result(api, run_id):
    for _ in range(100):
        result = api.get(f"/api/runs/{run_id}").json()
        if result["status"] not in ("pending", "running"):
            return result
        time.sleep(.03)
    raise AssertionError("Workflow did not finish")


def test_api_demo_workflow_and_history(tmp_path):
    with client(tmp_path) as api:
        response = api.post("/api/runs", json={"mode": "demo", "requirement": "ignored"})
        assert response.status_code == 202
        result = wait_result(api, response.json()["run_id"])
        assert result["status"] == "completed" and result["repairs"] == 1
        assert [m["receiver"] for m in result["messages"]] == ["code", "review", "fix", "review"]
        assert "return 0.0" in result["code"]
        assert "return 0.0" in result["diff"]
        assert api.get("/api/runs").json()[0]["run_id"] == result["run_id"]
        assert api.post(f'/api/runs/{result["run_id"]}/resume').status_code == 409


def test_api_invalid_input_and_paths(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/api/runs", json={"requirement": " "}).status_code == 422
        assert api.post("/api/runs", json={"mode": "bad"}).status_code == 422
        assert api.post("/api/runs", json={"requirement": "x", "source_code": "x" * 100001}).status_code == 422
        assert api.get("/api/runs/not-a-run").status_code == 400
        assert api.get("/api/runs/" + "0" * 32).status_code == 404


def test_workspace_serves_assets_and_settings_without_secret(tmp_path):
    with client(tmp_path) as api:
        assert 'workspace' in api.get("/").text
        assert api.get("/static/styles.css").status_code == 200
        assert api.get("/static/app.js").status_code == 200
        settings = api.get("/api/settings").json()
        assert isinstance(settings["configured"], bool)
        assert "api_key" not in settings and "sk-" not in str(settings)


def test_api_resume_starts_at_failed_node(tmp_path):
    from workflow.state import WorkflowState
    from workflow.storage import RunStore
    from workflow.demo import FIX
    state = WorkflowState(requirement="平均值", mode="demo", code=FIX, revisions=[FIX],
                          status="failed", next_node="review", steps=1)
    RunStore(tmp_path).save(state)
    with client(tmp_path) as api:
        assert api.post(f"/api/runs/{state.run_id}/resume").status_code == 202
        recovered = wait_result(api, state.run_id)
        assert recovered["status"] == "completed"
        assert recovered["revisions"] == [FIX]
        assert [m["receiver"] for m in recovered["messages"]] == ["review"]


def test_cross_origin_submission_and_utf8_size_rejected(tmp_path):
    with client(tmp_path) as api:
        assert api.post("/api/runs", json={"mode": "demo"},
                        headers={"Origin": "https://example.com"}).status_code == 403
        assert api.post("/api/runs", json={"requirement": "x", "source_code": "中" * 40000}).status_code == 422


def test_manager_rejects_duplicate_and_excess_jobs(tmp_path):
    from threading import Event
    from fastapi import HTTPException
    import pytest
    from web.server import RunManager
    from workflow.state import WorkflowState
    from workflow.storage import RunStore
    blocker = Event()

    class BlockingFlow:
        def run(self, state, on_event=None):
            assert blocker.wait(10)

    manager = RunManager(RunStore(tmp_path), lambda mode: BlockingFlow())
    first = WorkflowState(requirement="one")
    try:
        manager.start(first)
        with pytest.raises(HTTPException) as duplicate:
            manager.start(first)
        assert duplicate.value.status_code == 409
        manager.start(WorkflowState(requirement="two"))
        with pytest.raises(HTTPException) as capacity:
            manager.start(WorkflowState(requirement="three"))
        assert capacity.value.status_code == 429
    finally:
        blocker.set()
        manager.executor.shutdown(wait=True)


def test_interrupted_workspace_run_can_resume_after_server_restart(tmp_path):
    from workflow.state import WorkflowState, WorkflowEvent
    from workflow.storage import RunStore
    from workflow.demo import FIX
    state = WorkflowState(requirement="平均值", mode="demo", code=FIX, revisions=[FIX],
                          status="running", next_node="review", steps=1,
                          events=[WorkflowEvent(kind="workspace_accepted", node="code")])
    RunStore(tmp_path).save(state)
    with client(tmp_path) as api:
        recovered = api.get(f"/api/runs/{state.run_id}").json()
        assert recovered["status"] == "failed" and recovered["next_node"] == "review"
        assert api.post(f"/api/runs/{state.run_id}/resume").status_code == 202
        assert wait_result(api, state.run_id)["status"] == "completed"
