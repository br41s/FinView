"""Run the rollout step of cloudbuild.yaml against a fake `gcloud`.

`test_cloudbuild_policy.py` asserts what the script contains. These tests assert
what it does, because the 2026-09-30 gap was a logic error no string check could
see: build b28450be's `update-traffic` failed the startup probe, `bash -e` exited
on that line, and the rollback below it never ran. `spec.traffic` stayed on the
failed revision and every later `gcloud run deploy` refused to run until someone
restored the route by hand.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
PREVIOUS = "finview-api-d935ddc"
REVISION = "finview-api-1c929ab"
JOBS = ("geo-intel-cycle", "geo-intel-audit", "options-agent-cycle", "zonas-clave-cycle")

# Mirrors the parts of Cloud Run and Cloud Scheduler the rollout reads and writes.
# `update-traffic` writes spec.traffic before the revision proves it can start,
# exactly like the real command: a revision listed in `unservable` leaves spec on
# it, the service Ready=False and status.traffic where it was.
FAKE_GCLOUD = r'''
import json, sys
from pathlib import Path

state_path = Path(__file__).with_name("state.json")
state = json.loads(state_path.read_text())
args = sys.argv[1:]
flags = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
state["calls"].append(" ".join(args))


def save():
    state_path.write_text(json.dumps(state))


def service():
    return {
        "spec": {"traffic": state["spec_traffic"]},
        "status": {
            "traffic": state["status_traffic"],
            "conditions": [{"type": "Ready", "status": "True" if state["ready"] else "False"}],
            "latestCreatedRevisionName": state["latest"],
        },
    }


save()
if args[:2] == ["builds", "describe"]:
    print("trigger-1")
elif args[:2] == ["builds", "list"]:
    print(json.dumps([{"id": "build-1", "createTime": "2026-09-30T10:00:00Z",
                       "buildTriggerId": "trigger-1"}]))
elif args[:3] == ["run", "services", "describe"]:
    if flags["format"].startswith("value("):
        print(state["latest"])
    else:
        print(json.dumps(service()))
elif args[:3] == ["run", "services", "update-traffic"]:
    target = flags["to-revisions"].rsplit("=", 1)[0]
    if state["reject_before_write"]:
        sys.exit("ERROR: (gcloud.run.services.update-traffic) PERMISSION_DENIED")
    state["spec_traffic"] = [{"revisionName": target, "percent": 100}]
    if target in state["unservable"]:
        state["ready"] = False
        save()
        sys.exit(f"ERROR: Revision '{target}' is not ready and cannot serve traffic.")
    state["status_traffic"] = [{"revisionName": target, "percent": 100}]
    state["ready"] = True
    save()
elif args[:3] == ["scheduler", "jobs", "describe"]:
    print(state["jobs"][args[3]])
elif args[:3] == ["scheduler", "jobs", "pause"]:
    state["jobs"][args[3]] = "PAUSED"
    save()
elif args[:3] == ["scheduler", "jobs", "resume"]:
    if state["jobs"][args[3]] == "ENABLED":
        sys.exit("ERROR: FAILED_PRECONDITION")
    state["jobs"][args[3]] = "ENABLED"
    save()
else:
    sys.exit(f"fake gcloud: unhandled {args}")
'''


def _rollout_script() -> str:
    steps = yaml.safe_load((ROOT / "cloudbuild.yaml").read_text())["steps"]
    [step] = [s for s in steps if "update-traffic" in json.dumps(s)]
    script = step["args"][-1]
    # Cloud Build substitutions first, then its `$$` escape for a literal `$`.
    values = {"PROJECT_ID": "finview-test", "BUILD_ID": "build-1", "SHORT_SHA": "1c929ab"}
    script = re.sub(
        r"(?<!\$)\$(PROJECT_ID|BUILD_ID|SHORT_SHA)\b", lambda m: values[m.group(1)], script
    )
    return script.replace("$$", "$")


def _run(tmp_path: Path, *, unservable=(), reject_before_write=False):
    state = {
        "spec_traffic": [{"revisionName": PREVIOUS, "percent": 100}],
        "status_traffic": [{"revisionName": PREVIOUS, "percent": 100}],
        "ready": True,
        "latest": REVISION,
        "unservable": list(unservable),
        "reject_before_write": reject_before_write,
        "jobs": dict.fromkeys(JOBS, "ENABLED"),
        "calls": [],
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "state.json").write_text(json.dumps(state))
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(f"#!{sys.executable}\n{FAKE_GCLOUD}")
    gcloud.chmod(0o755)
    # The guard script has its own tests; here it only has to pass.
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "verify_cloud_run_service.py").write_text("")

    result = subprocess.run(
        ["bash", "-ceu", _rollout_script()],
        cwd=tmp_path,
        env={"PATH": f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, json.loads((bin_dir / "state.json").read_text())


def _traffic_writes(state: dict) -> list[str]:
    return [c for c in state["calls"] if c.startswith("run services update-traffic")]


def test_successful_promotion_moves_traffic_and_resumes_callers(tmp_path):
    result, state = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert state["spec_traffic"] == [{"revisionName": REVISION, "percent": 100}]
    assert state["status_traffic"] == [{"revisionName": REVISION, "percent": 100}]
    assert set(state["jobs"].values()) == {"ENABLED"}


def test_failed_promotion_restores_previous_revision_in_spec(tmp_path):
    """The 2026-09-30 incident: the candidate cannot start, so promotion fails.

    Before the fix the build ended here with spec.traffic on the failed revision
    and the service Ready=False, which is what blocked the next deploy.
    """
    result, state = _run(tmp_path, unservable=[REVISION])

    assert result.returncode != 0
    assert state["spec_traffic"] == [{"revisionName": PREVIOUS, "percent": 100}]
    assert state["status_traffic"] == [{"revisionName": PREVIOUS, "percent": 100}]
    assert state["ready"] is True
    assert f"traffic restored to {PREVIOUS}" in result.stdout
    # Back on a serving revision, so periodic callers run again.
    assert set(state["jobs"].values()) == {"ENABLED"}


def test_callers_stay_paused_when_the_restore_does_not_converge(tmp_path):
    result, state = _run(tmp_path, unservable=[REVISION, PREVIOUS])

    assert result.returncode != 0
    assert f"Restore to {PREVIOUS} did not converge" in result.stdout
    assert set(state["jobs"].values()) == {"PAUSED"}


def test_failed_promotion_that_never_wrote_spec_restores_nothing(tmp_path):
    """Only this build's own write is undone: if spec.traffic does not hold it,
    there is nothing of ours to restore and traffic is not touched again."""
    result, state = _run(tmp_path, reject_before_write=True)

    assert result.returncode != 0
    assert _traffic_writes(state) == [
        f"run services update-traffic finview-api --project=finview-test "
        f"--region=europe-west1 --to-revisions={REVISION}=100 --quiet"
    ]
    assert state["spec_traffic"] == [{"revisionName": PREVIOUS, "percent": 100}]
    assert set(state["jobs"].values()) == {"ENABLED"}
