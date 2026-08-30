from pathlib import Path

import pytest

from hermes_jarvis.store import ProfileNotFound, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "orbitylabs.db")


def test_unknown_profile_raises(store: Store) -> None:
    with pytest.raises(ProfileNotFound):
        store.list_agents("missing")
    with pytest.raises(ProfileNotFound):
        store.create_task("missing", "t1", "Title", "Area", "draft")


def test_profiles_are_isolated(store: Store) -> None:
    business = store.create_profile("biz", "Business", "Business", "", "")
    personal = store.create_profile("personal", "Personal projects", "Personal", "", "")

    store.create_agent("biz", "ceo", "CEO", "Strategy", "CE")
    store.create_agent("personal", "helper", "Helper", "Chores", "HP")
    store.create_task("biz", "t1", "Ship the launch", "Growth", "draft")
    store.create_source("personal", "s1", "Recipe notes", "Local file")

    biz_agents = store.list_agents("biz")
    personal_agents = store.list_agents("personal")
    assert [a["id"] for a in biz_agents] == ["ceo"]
    assert [a["id"] for a in personal_agents] == ["helper"]

    assert store.list_tasks("personal") == []
    assert len(store.list_tasks("biz")) == 1

    assert store.list_sources("biz") == []
    assert len(store.list_sources("personal")) == 1

    assert business["id"] == "biz"
    assert personal["id"] == "personal"


def test_task_lifecycle_is_scoped_to_its_profile(store: Store) -> None:
    store.create_profile("a", "A", "", "", "")
    store.create_profile("b", "B", "", "", "")
    store.create_task("a", "shared-id", "Task in A", "General", "draft")

    with pytest.raises(LookupError):
        store.update_task("b", "shared-id", "live")

    store.update_task("a", "shared-id", "live")
    assert store.list_tasks("a")[0]["state"] == "live"

    store.delete_task("b", "shared-id")
    assert len(store.list_tasks("a")) == 1


def test_policy_defaults_to_manual_and_is_scoped(store: Store) -> None:
    store.create_profile("a", "A", "", "", "")
    store.create_profile("b", "B", "", "", "")
    assert store.get_policy("a")["autonomy"] == "manual"

    store.set_policy("a", "auto_safe")
    assert store.get_policy("a")["autonomy"] == "auto_safe"
    assert store.get_policy("b")["autonomy"] == "manual"

    with pytest.raises(ValueError):
        store.set_policy("a", "not-a-real-mode")


def test_model_routes_are_per_agent_and_per_profile(store: Store) -> None:
    store.create_profile("a", "A", "", "", "")
    store.set_model_route("a", "", "openrouter", "gpt-4.1")
    store.set_model_route("a", "ceo", "anthropic", "claude-sonnet-5")

    routes = store.list_model_routes("a")
    assert routes["default"] == {"provider": "openrouter", "model": "gpt-4.1"}
    assert routes["ceo"] == {"provider": "anthropic", "model": "claude-sonnet-5"}
    assert "chief" not in routes


def test_events_are_recorded_and_scoped(store: Store) -> None:
    store.create_profile("a", "A", "", "", "")
    store.create_profile("b", "B", "", "", "")
    store.record_event("a", "run.created", {"run_id": "1"})
    store.record_event("b", "run.created", {"run_id": "2"})

    a_events = store.list_events("a")
    assert len(a_events) == 1
    assert a_events[0]["data"]["run_id"] == "1"


def test_global_context_carries_profile_provenance(store: Store) -> None:
    store.create_profile("biz", "Business", "Business", "Runs the shop", "")
    store.create_agent("biz", "ceo", "CEO", "Strategy", "CE")
    store.create_source("biz", "s1", "Playbook", "Notes")

    context = store.global_context()
    assert len(context) == 1
    assert context[0]["profile_id"] == "biz"
    assert context[0]["name"] == "Business"
    assert context[0]["agents"] == [{"name": "CEO", "role": "Strategy"}]
    assert context[0]["sources"] == ["Playbook"]


def test_agent_output_and_continuous_loop_are_profile_scoped(store: Store) -> None:
    store.create_profile("a", "A", "", "", "/tmp/vault-a")
    store.create_profile("b", "B", "", "", "/tmp/vault-b")
    store.create_agent("a", "ceo", "CEO", "Operations", "CE", "/tmp/agent-a", True, True, 120)

    candidates = store.agent_loop_candidates()
    assert len(candidates) == 1
    assert candidates[0]["profile_id"] == "a"
    assert candidates[0]["output_path"] == "/tmp/agent-a"
    assert candidates[0]["mirror_to_vault"] == 1
    assert candidates[0]["interval_seconds"] == 120

    store.mark_agent_loop("a", "ceo", run_id="run-1")
    assert store.agent_loop_candidates()[0]["last_run_id"] == "run-1"


def test_paired_device_secret_is_hashed_and_manifest_has_no_secret(store: Store) -> None:
    store.create_profile("a", "A", "", "Private context", "/tmp/vault-a")
    store.create_agent("a", "ceo", "CEO", "Operations", "CE")
    store.register_paired_device("device-1", "hashed-secret", "Phone")

    assert store.verify_paired_device("hashed-secret") is True
    assert store.verify_paired_device("wrong-secret") is False
    manifest = store.mobile_manifest()
    assert manifest == [{"id": "a", "name": "A", "kind": "", "context": "Private context", "agents": [{"id": "ceo", "name": "CEO", "role": "Operations", "initials": "CE"}]}]


def test_skill_matching_and_drafts_stay_profile_scoped(store: Store) -> None:
    store.create_profile("a", "A", "", "", "")
    store.create_profile("b", "B", "", "", "")
    store.create_agent("a", "ceo", "CEO", "Operations", "CE")
    store.create_skill("a", "github", "GitHub review", "https://github.com/example/github-review", "Review pull requests and repository changes")

    matches = store.match_skills("a", "Review the current pull request")
    assert [match["id"] for match in matches] == ["github"]
    assert store.match_skills("b", "Review the current pull request") == []

    draft = store.create_skill_draft("a", "ceo", "Create a release-review skill", "run-1")
    assert draft["status"] == "requested"
    assert draft["run_id"] == "run-1"
