#!/usr/bin/env python3
"""Fail-closed Cloud Run deployment and cost-safety verification."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _annotation_int(annotations: dict[str, str], key: str, default: int) -> int:
    raw = annotations.get(key)
    return default if raw in (None, "") else int(raw)


def validate_service(
    service: dict[str, Any],
    *,
    expected_revision: str,
    phase: str,
) -> list[str]:
    """Return invariant violations without printing service configuration."""
    errors: list[str] = []
    status = service.get("status", {})
    conditions = {row.get("type"): row for row in status.get("conditions", [])}
    ready = conditions.get("Ready", {})
    if ready.get("status") != "True":
        errors.append(f"service Ready is {ready.get('status', 'missing')}")

    latest_created = status.get("latestCreatedRevisionName")
    latest_ready = status.get("latestReadyRevisionName")
    if latest_created != expected_revision:
        errors.append(
            f"latest created revision is {latest_created!r}, expected {expected_revision!r}"
        )
    if latest_ready != expected_revision:
        errors.append(
            f"latest ready revision is {latest_ready!r}, expected {expected_revision!r}"
        )

    metadata_annotations = service.get("metadata", {}).get("annotations", {})
    template = service.get("spec", {}).get("template", {})
    template_annotations = template.get("metadata", {}).get("annotations", {})

    if template_annotations.get("run.googleapis.com/cpu-throttling") == "false":
        errors.append("instance-based billing is enabled (cpu-throttling=false)")

    service_min = _annotation_int(metadata_annotations, "run.googleapis.com/minScale", 0)
    revision_min = _annotation_int(
        template_annotations, "autoscaling.knative.dev/minScale", 0
    )
    if service_min != 0 or revision_min != 0:
        errors.append(
            f"minimum instances must be zero (service={service_min}, revision={revision_min})"
        )

    service_max_raw = metadata_annotations.get("run.googleapis.com/maxScale")
    revision_max_raw = template_annotations.get("autoscaling.knative.dev/maxScale")
    if service_max_raw in (None, ""):
        errors.append("service maximum instances is not explicitly configured")
    if revision_max_raw in (None, ""):
        errors.append("revision maximum instances is not explicitly configured")
    service_max = int(service_max_raw) if service_max_raw not in (None, "") else 0
    revision_max = int(revision_max_raw) if revision_max_raw not in (None, "") else 0
    if service_max > 1 or revision_max > 1:
        errors.append(
            f"maximum instances exceeds cost cap (service={service_max}, revision={revision_max})"
        )

    containers = template.get("spec", {}).get("containers", [])
    ports = containers[0].get("ports", []) if containers else []
    container_port = ports[0].get("containerPort") if ports else None
    if container_port != 8080:
        errors.append(f"container port is {container_port!r}, expected 8080")

    traffic = status.get("traffic", [])
    if phase == "candidate":
        if any(
            row.get("revisionName") == expected_revision and (row.get("percent") or 0) > 0
            for row in traffic
        ):
            errors.append("candidate revision received production traffic before verification")
    else:
        live_percent = sum(
            row.get("percent") or 0
            for row in traffic
            if row.get("revisionName") == expected_revision
        )
        if live_percent != 100:
            errors.append(
                f"live revision has {live_percent}% traffic instead of 100%"
            )

    return errors


def _load_service(project: str, region: str, service: str) -> dict[str, Any]:
    fields = (
        "metadata.name,metadata.annotations,spec.template.metadata.annotations,"
        "spec.template.spec.containers[].ports,status.conditions,"
        "status.latestCreatedRevisionName,status.latestReadyRevisionName,"
        "status.traffic,status.url"
    )
    result = subprocess.run(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service,
            f"--project={project}",
            f"--region={region}",
            f"--format=json({fields})",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _health_url(service: dict[str, Any]) -> str:
    status = service.get("status", {})
    return f"{status['url'].rstrip('/')}/api/health/ready"


def _check_health(url: str, timeout: float, attempts: int) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
                payload = json.load(response)
            if (
                payload.get("status") == "ready"
                and payload.get("database") == "startup-ok"
                and payload.get("environment") == "production"
                and payload.get("runtime") == "request-scoped"
            ):
                return
            last_error = RuntimeError(
                "readiness payload does not confirm request-scoped startup"
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(5)
    raise RuntimeError(
        f"readiness request failed after {attempts} attempts: "
        f"{last_error.__class__.__name__ if last_error else 'unknown'}"
    ) from last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--phase", choices=("candidate", "live"), required=True)
    parser.add_argument("--health-timeout", type=float, default=30)
    parser.add_argument("--health-attempts", type=int, default=6)
    args = parser.parse_args()

    service = _load_service(args.project, args.region, args.service)
    errors = validate_service(
        service,
        expected_revision=args.revision,
        phase=args.phase,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.phase == "live":
        try:
            _check_health(
                _health_url(service),
                args.health_timeout,
                args.health_attempts,
            )
        except (KeyError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print(
        f"Cloud Run guard passed: {args.service} {args.revision} "
        f"phase={args.phase} request-billed min=0 max=1 startup=ready"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
