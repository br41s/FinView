"""Tests for fail-closed Cloud Run deployment invariants."""

from copy import deepcopy

from scripts.verify_cloud_run_service import validate_revision, validate_service


def _service(phase: str = "live") -> dict:
    """Mirror the shape `gcloud run deploy` actually produces.

    Both scaling scopes are pinned: `--max` writes the service-level
    `run.googleapis.com/maxScale`, `--max-instances` writes the revision
    template's `autoscaling.knative.dev/maxScale`.
    """
    traffic = [
        {
            "revisionName": "finview-api-00123-safe",
            "percent": 100,
        }
    ]
    if phase == "candidate":
        traffic = [
            {"revisionName": "finview-api-00121-old", "percent": 100},
        ]
    return {
        "metadata": {"annotations": {"run.googleapis.com/maxScale": "1"}},
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "autoscaling.knative.dev/maxScale": "1",
                        "run.googleapis.com/cpu-throttling": "true",
                    }
                },
                "spec": {"containers": [{"ports": [{"containerPort": 8080}]}]},
            }
        },
        "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "latestCreatedRevisionName": "finview-api-00123-safe",
            "latestReadyRevisionName": "finview-api-00123-safe",
            "traffic": traffic,
            "url": "https://finview-api.example.run.app",
        },
    }


def _errors(service: dict, phase: str = "live") -> list[str]:
    return validate_service(
        service,
        expected_revision="finview-api-00123-safe",
        phase=phase,
    )


def _revision() -> dict:
    return {
        "metadata": {
            "name": "finview-api-00123-safe",
            "annotations": {
                "autoscaling.knative.dev/maxScale": "1",
                "run.googleapis.com/cpu-throttling": "true",
            },
        },
        "spec": {"containers": [{"ports": [{"containerPort": 8080}]}]},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }


def test_live_service_passes_all_safety_invariants():
    assert _errors(_service()) == []


def test_candidate_passes_without_receiving_production_traffic():
    service = _service("candidate")
    service["status"]["latestReadyRevisionName"] = "finview-api-00121-old"

    assert _errors(service, "candidate") == []
    assert validate_revision(
        _revision(), expected_revision="finview-api-00123-safe"
    ) == []


def test_candidate_rejects_revision_that_is_not_ready():
    revision = _revision()
    revision["status"]["conditions"][0]["status"] = "False"

    errors = validate_revision(
        revision, expected_revision="finview-api-00123-safe"
    )

    assert any("revision Ready is False" in error for error in errors)


def test_rejects_instance_billing_minimums_scaleout_and_wrong_port():
    service = _service()
    annotations = service["spec"]["template"]["metadata"]["annotations"]
    annotations["run.googleapis.com/cpu-throttling"] = "false"
    annotations["autoscaling.knative.dev/minScale"] = "1"
    annotations["autoscaling.knative.dev/maxScale"] = "3"
    service["spec"]["template"]["spec"]["containers"][0]["ports"][0][
        "containerPort"
    ] = 8000

    errors = _errors(service)

    assert any("instance-based billing" in error for error in errors)
    assert any("minimum instances" in error for error in errors)
    assert any("cost cap" in error for error in errors)
    assert any("expected 8080" in error for error in errors)


def test_rejects_manual_scaling_because_it_overrides_autoscaling_limits():
    """A manually scaled service pins instances up regardless of minScale, so
    the annotations this guard reads would report a safe configuration that
    Cloud Run is not applying."""
    service = _service()
    service["metadata"]["annotations"].update(
        {
            "run.googleapis.com/scalingMode": "manual",
            "run.googleapis.com/manualInstanceCount": "1",
        }
    )

    errors = _errors(service)

    assert any("manual scaling" in error for error in errors)


def test_accepts_explicit_automatic_scaling():
    service = _service()
    service["metadata"]["annotations"]["run.googleapis.com/scalingMode"] = "automatic"

    assert _errors(service) == []


def test_rejects_missing_explicit_service_and_revision_maximums():
    service = _service()
    del service["metadata"]["annotations"]["run.googleapis.com/maxScale"]
    del service["spec"]["template"]["metadata"]["annotations"][
        "autoscaling.knative.dev/maxScale"
    ]

    errors = _errors(service)

    assert any("service maximum" in error for error in errors)
    assert any("revision maximum" in error for error in errors)


def test_rejects_service_maximum_that_drifted_above_the_revision_cap():
    """Regression for 2026-08-05: switching the paused service back to
    `--scaling=auto` set a service-level maximum of 3 while the revision stayed
    at 1, because #198 had stopped the deploy passing `--max`. The effective cap
    was still 1, but nothing was pinning the service scope any more."""
    service = _service()
    service["metadata"]["annotations"]["run.googleapis.com/maxScale"] = "3"

    errors = _errors(service)

    assert any("cost cap" in error and "service=3" in error for error in errors)


def test_rejects_failed_or_unpromoted_revision():
    service = deepcopy(_service())
    service["status"]["conditions"][0]["status"] = "False"
    service["status"]["latestReadyRevisionName"] = "finview-api-00121-old"
    service["status"]["traffic"] = [
        {"revisionName": "finview-api-00121-old", "percent": 100}
    ]

    errors = _errors(service)

    assert any("Ready is False" in error for error in errors)
    assert any("latest ready revision" in error for error in errors)
    assert any("0% traffic instead of 100%" in error for error in errors)
