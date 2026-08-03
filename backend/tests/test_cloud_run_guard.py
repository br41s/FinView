"""Tests for fail-closed Cloud Run deployment invariants."""

from copy import deepcopy

from scripts.verify_cloud_run_service import validate_revision, validate_service


def _service(phase: str = "live") -> dict:
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


def test_rejects_missing_explicit_service_and_revision_maximums():
    service = _service()
    del service["metadata"]["annotations"]["run.googleapis.com/maxScale"]
    del service["spec"]["template"]["metadata"]["annotations"][
        "autoscaling.knative.dev/maxScale"
    ]

    errors = _errors(service)

    assert any("service maximum" in error for error in errors)
    assert any("revision maximum" in error for error in errors)


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
