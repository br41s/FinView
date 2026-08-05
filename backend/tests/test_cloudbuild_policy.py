"""Regression tests for Cloud Run cost and rollout policy."""

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def _steps() -> list[dict]:
    return yaml.safe_load((ROOT / "cloudbuild.yaml").read_text())["steps"]


def _index_of(fragment: str) -> int:
    """Locate a step by what it does, so inserting steps cannot silently
    repoint an assertion at the wrong one."""
    matches = [i for i, step in enumerate(_steps()) if fragment in json.dumps(step)]
    assert len(matches) == 1, (
        f"expected exactly one build step containing {fragment!r}, found {len(matches)}"
    )
    return matches[0]


def _step(fragment: str) -> dict:
    return _steps()[_index_of(fragment)]


def test_suite_gates_the_build_before_the_image_is_published():
    test_index = _index_of("python -m pytest")
    push_index = _index_of('"push"')

    assert test_index < push_index

    test_step = _steps()[test_index]
    assert "--volume" in json.dumps(test_step)
    assert "PYTHONPATH=/workspace" in json.dumps(test_step)


def test_deploy_is_request_billed_bounded_and_fail_closed():
    deploy_args = _step("--revision-suffix=$SHORT_SHA")["args"]

    assert "--cpu-throttling" in deploy_args
    assert "--no-cpu-throttling" not in deploy_args
    assert "--min-instances=0" in deploy_args
    assert "--max-instances=1" in deploy_args
    assert "--no-traffic" in deploy_args
    assert "--revision-suffix=$SHORT_SHA" in deploy_args
    assert (
        "--update-env-vars=FINVIEW_ENV=production,"
        "FINVIEW_REQUEST_SCOPED_RUNTIME=true"
    ) in deploy_args


def test_deploy_pins_both_service_and_revision_scaling_scopes():
    """`--min`/`--max` are service-level; `--min-instances`/`--max-instances` are
    revision-level. They are not aliases -- the effective cap is the lower of the
    two, so leaving either scope unpinned lets that scope drift."""
    deploy_args = _step("--revision-suffix=$SHORT_SHA")["args"]

    assert "--min=0" in deploy_args
    assert "--max=1" in deploy_args
    assert "--min-instances=0" in deploy_args
    assert "--max-instances=1" in deploy_args


def test_rollout_serializes_builds_and_pauses_periodic_callers():
    rollout = _step("update-traffic")["args"][-1]

    assert "gcloud builds cancel" in rollout
    assert "did not stop; refusing to change traffic" in rollout
    assert "gcloud scheduler jobs pause" in rollout
    assert '"$$LIVE" = "$$REVISION"' in rollout
    assert '"$$LATEST" = "$$REVISION"' in rollout
