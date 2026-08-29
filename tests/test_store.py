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
