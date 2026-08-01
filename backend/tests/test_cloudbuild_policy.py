"""Regression tests for Cloud Run cost and rollout policy."""

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def _steps() -> list[dict]:
    return yaml.safe_load((ROOT / "cloudbuild.yaml").read_text())["steps"]


def test_deploy_is_request_billed_bounded_and_fail_closed():
    deploy_args = _steps()[3]["args"]

    assert "--cpu-throttling" in deploy_args
    assert "--no-cpu-throttling" not in deploy_args
    assert "--min=0" in deploy_args
    assert "--max=1" in deploy_args
    assert "--max-instances=1" in deploy_args
    assert "--no-traffic" in deploy_args
    assert "--revision-suffix=$SHORT_SHA" in deploy_args
    assert (
        "--update-env-vars=FINVIEW_ENV=production,"
        "FINVIEW_REQUEST_SCOPED_RUNTIME=true"
    ) in deploy_args


def test_rollout_serializes_builds_and_pauses_periodic_callers():
    rollout = _steps()[4]["args"][-1]

    assert "gcloud builds cancel" in rollout
    assert "did not stop; refusing to change traffic" in rollout
    assert "gcloud scheduler jobs pause" in rollout
    assert '"$$LIVE" = "$$REVISION"' in rollout
    assert '"$$LATEST" = "$$REVISION"' in rollout
