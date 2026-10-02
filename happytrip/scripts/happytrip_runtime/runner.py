"""Local checkpointed handoff. Native calls remain the host agent's responsibility."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from PIL import Image

from .assets import resolve_assets
from .catalog import load_catalog, get_mode
from .router import recommend
from .planner import make_plan
from .compiler import build_context, compile_prompt
from .types import HappyTripError

REVIEW_CHECKS = {"mode_visual", "identity_and_subjects", "facts_and_text", "edit_scope"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextmanager
def _lock(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield root


def _check_private(data, allow_coordinates=False):
    # Requests are local data, but credentials never belong in persisted job records.
    if isinstance(data, dict):
        for key, value in data.items():
            if re.search(r"(?:api[_-]?key|password|authorization|secret|access[_-]?token)", key, re.I):
                raise HappyTripError("PRIVATE_DATA", "Credentials must not be included in requests")
            if not allow_coordinates and key.lower() in {"lat", "lon", "latitude", "longitude", "coordinates", "gps"}:
                raise HappyTripError("PRIVATE_DATA", "Geographic coordinates require a geographic request")
            _check_private(value, allow_coordinates=allow_coordinates)
    elif isinstance(data, list):
        for item in data:
            _check_private(item, allow_coordinates=allow_coordinates)
    elif isinstance(data, str) and re.search(r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+\S+|[?&](?:token|key|signature)=)", data, re.I):
        raise HappyTripError("PRIVATE_DATA", "Do not persist credentials or signed URLs")


def _check_request_privacy(request):
    # Scan inside coordinate records too: permitting geodata never permits secrets.
    if not isinstance(request, dict) or not isinstance(request.get("mode_options", {}), dict):
        raise HappyTripError("INPUT_INVALID", "Request and mode_options must be objects.")
    _check_private(request, allow_coordinates=request.get("mode_options", {}).get("map_mode") == "geographic")


def _validate_image(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise HappyTripError("ASSET_MISSING", "Image file does not exist")
    try:
        with Image.open(path) as im:
            if im.format not in {"PNG", "JPEG", "WEBP", "TIFF"}:
                raise ValueError("unsupported image")
            im.verify()
    except Exception as exc:
        raise HappyTripError("ASSET_INVALID", "Unreadable image file") from exc
    return path


def _base_result(root, mode=None):
    return {"job_id": root.name, "mode": mode, "status": "needs_input", "image_assets": [],
            "candidate_assets": [], "warnings": [], "errors": [], "caption": None,
            "validation_status": "not_run", "actual_cost": None, "image_calls": 0,
            "provider_request_ids": []}


def prepare_job(request, adapter, store):
    _check_request_privacy(request)
    with _lock(store) as root:
        existing = root / "state.json"
        if existing.exists():
            state = read_json(existing)
            if state["request_fingerprint"] != _fingerprint(request):
                raise HappyTripError("JOB_CONFLICT", "Use a new job directory for a changed request")
            return read_json(root / "result.json")
        result = _base_result(root)
        write_json(root / "request.json", request)
        write_json(root / "validation.json", {"status": "not_run", "checks": []})
        plan = {"status": "needs_input", "stages": [], "errors": []}
        assets = []
        try:
            assets = resolve_assets(request, workdir=root / "assets")
            catalog = load_catalog()
            suggestions = recommend(request, assets, catalog)
            result["recommendations"] = suggestions
            explicit = request.get("mode", "auto") != "auto"
            intent_selected = len(suggestions) == 1 and suggestions[0].get("selection") in {"explicit", "intent"}
            if not suggestions:
                raise HappyTripError("MODE_UNKNOWN", "No compatible mode was selected")
            if not explicit and not request.get("auto_select", False) and not intent_selected:
                raise HappyTripError("MODE_SELECTION_REQUIRED", "Choose a recommended mode or authorize automatic selection")
            mode = get_mode(catalog, suggestions[0]["mode"])
            plan = make_plan(request, assets, mode, adapter.capabilities())
            result["mode"] = mode["id"]
            result["status"] = plan["status"]
            result["errors"] = plan.get("errors", [])
            result["warnings"] = plan.get("warnings", [])
            if plan["status"] in {"ready", "prompt_only", "needs_capability"}:
                context = build_context(request, assets, plan)
                context["layout_summary"] = json.dumps({
                    "ratio": request.get("output", {}).get("ratio", mode["default_ratio"]),
                    "language": request.get("output", {}).get("language", "zh")}, ensure_ascii=False)
                prompt = compile_prompt(mode, context)
                by_id = {a["photo_id"]: a for a in assets}
                for stage in plan["stages"]:
                    if stage["kind"] != "generate":
                        continue
                    sid = stage["id"]
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
                        raise HappyTripError("PLAN_INVALID", "Unsafe stage ID")
                    stage_prompt = prompt + "\n当前只执行这个单元：" + stage["instruction"]
                    stage_prompt += "\n单元数据：" + json.dumps(stage.get("unit", {}), ensure_ascii=False)
                    (root / "prompts").mkdir(exist_ok=True)
                    (root / "prompts" / (sid + ".txt")).write_text(stage_prompt, encoding="utf-8")
                    image_request = {"mode": mode["id"], "stage_id": sid, "prompt": stage_prompt,
                                     "references": [by_id[p]["working_path"] for p in stage["photo_ids"]],
                                     "output_dir": str(root / "candidates"),
                                     "transparent_background": mode["id"] == "A07" and stage.get("unit", {}).get("type") == "sticker",
                                     "idempotency_key": _fingerprint(request) + ":" + sid}
                    write_json(root / "image-requests" / (sid + ".json"), image_request)
        except HappyTripError as exc:
            result["status"] = "needs_input"
            result["errors"] = [{"code": exc.code, "message": str(exc)}]
            plan["status"] = "needs_input"
            plan["errors"] = result["errors"]
        write_json(root / "assets.json", assets)
        write_json(root / "plan.json", plan)
        write_json(root / "state.json", {"request_fingerprint": _fingerprint(request), "image_calls": 0,
                                        "cancelled": False, "stages": {}, "call_history": [], "simulated": False})
        write_json(root / "result.json", result)
        return result


def _sync_result(root, state):
    result = read_json(root / "result.json")
    history = state.setdefault("call_history", [])
    for stage in state["stages"].values():
        key = (stage["stage_id"], stage.get("attempts"))
        index = next((i for i, call in enumerate(history) if (call["stage_id"], call.get("attempts")) == key), None)
        if index is None:
            history.append(dict(stage))
        else:
            history[index] = dict(stage)
    result["image_calls"] = state["image_calls"]
    result["candidate_assets"] = [v for v in state["stages"].values() if v.get("path")]
    result["provider_request_ids"] = [v["provider_request_id"] for v in history
                                      if v.get("provider_request_id")]
    costs = [v.get("actual_cost") for v in history if v.get("attempts", 0)]
    result["actual_cost"] = sum(costs) if costs and all(type(c) in (int, float) for c in costs) else None
    if state["cancelled"]:
        result["status"] = "cancelled"
    elif any(s.get("status") in {"unknown", "running"} for s in state["stages"].values()):
        result["status"] = "running"
    elif any(s.get("status") == "failed" for s in state["stages"].values()):
        result["status"] = "failed"
    elif result["candidate_assets"]:
        result["status"] = "completed_with_warning"
        result["warnings"] = list(dict.fromkeys(result.get("warnings", []) + ["候选已保存；合成或视觉验收尚未完成。"]))
    write_json(root / "state.json", state)
    write_json(root / "result.json", result)
    return result


def reserve_stage(store, stage_id):
    with _lock(store) as root:
        state, plan = read_json(root / "state.json"), read_json(root / "plan.json")
        if state["cancelled"]:
            raise HappyTripError("CANCELLED", "Job is cancelled")
        if plan["status"] != "ready":
            raise HappyTripError("PLAN_NOT_READY", "Resolve the plan's inputs or capability gaps before calling tools")
        stage = next((s for s in plan["stages"] if s["id"] == stage_id and s["kind"] == "generate"), None)
        if not stage:
            raise HappyTripError("STAGE_UNKNOWN", "Unknown generation stage")
        for dependency in stage.get("depends_on", []):
            if state["stages"].get(dependency, {}).get("status") != "candidate":
                raise HappyTripError("DEPENDENCY_PENDING", f"Stage {dependency} is not available")
        current = state["stages"].get(stage_id, {})
        if current.get("status") in {"running", "unknown"}:
            raise HappyTripError("CALL_STATUS_UNKNOWN", "Query or import the original call; do not submit it again")
        if current.get("status") == "candidate":
            raise HappyTripError("STAGE_COMPLETE", "Keep this candidate; mark a verified failure before requesting repair")
        budget = plan["call_budget"]
        if state["image_calls"] >= budget["max_image_calls"] or current.get("attempts", 0) >= 1 + budget["max_repairs_per_stage"]:
            raise HappyTripError("BUDGET_EXCEEDED", "Image-call budget exhausted; use an explicitly approved revised plan")
        for asset in read_json(root / "assets.json"):
            if digest(asset["working_path"]) != asset["working_sha256"]:
                raise HappyTripError("ASSET_CHANGED", "A registered working image has changed")
        image_request = read_json(root / "image-requests" / (stage_id + ".json"))
        attempts = current.get("attempts", 0) + 1
        image_request["idempotency_key"] += f":{attempts}"
        state["image_calls"] += 1
        state["stages"][stage_id] = {"stage_id": stage_id, "status": "running", "attempts": attempts,
                                    "idempotency_key": image_request["idempotency_key"]}
        _sync_result(root, state)
        return image_request


def import_candidate(store, stage_id, image_path, *, simulated=False, provider_request_id=None, actual_cost=None):
    source = _validate_image(image_path)
    with _lock(store) as root:
        state = read_json(root / "state.json")
        if state["cancelled"]:
            raise HappyTripError("CANCELLED", "Job is cancelled")
        current = state["stages"].get(stage_id, {})
        if current.get("status") not in {"running", "unknown"}:
            raise HappyTripError("CALL_NOT_RESERVED", "Reserve a generation call before importing its file")
        target = root / "candidates" / (stage_id + "-" + str(current["attempts"]) + source.suffix.lower())
        target.parent.mkdir(exist_ok=True)
        if source != target.resolve():
            if target.exists():
                raise HappyTripError("OUTPUT_EXISTS", "Candidate destination already exists")
            shutil.copyfile(source, target)
        if provider_request_id:
            _check_private(provider_request_id)
        if actual_cost is not None and (type(actual_cost) not in (int, float) or actual_cost < 0):
            raise HappyTripError("COST_INVALID", "Cost must be a measured nonnegative number or null")
        current.update(status="candidate", path=str(target), sha256=digest(target), simulated=bool(simulated),
                       provider_request_id=provider_request_id, actual_cost=actual_cost)
        state["simulated"] = state["simulated"] or bool(simulated)
        return _sync_result(root, state)


def record_failure(store, stage_id, status="unknown"):
    if status not in {"failed", "unknown"}:
        raise HappyTripError("STATUS_INVALID", "Use failed or unknown")
    with _lock(store) as root:
        state = read_json(root / "state.json")
        current = state["stages"].get(stage_id)
        if not current:
            raise HappyTripError("CALL_NOT_RESERVED", "No recorded call for this stage")
        if current["status"] == "unknown" and status == "failed":
            raise HappyTripError("CALL_STATUS_UNKNOWN", "Unknown calls need provider reconciliation, not automatic repair")
        current["status"] = status
        return _sync_result(root, state)


def cancel_job(store):
    with _lock(store) as root:
        state = read_json(root / "state.json")
        state["cancelled"] = True
        return _sync_result(root, state)


def run_job(request, adapter, store):
    result = prepare_job(request, adapter, store)
    root = Path(store).resolve()
    state, plan = read_json(root / "state.json"), read_json(root / "plan.json")
    if state["cancelled"] or plan["status"] != "ready":
        return result
    if getattr(adapter, "deferred", False):
        with _lock(root):
            result["status"] = "prompt_only"
            write_json(root / "result.json", result)
        return result
    for stage in plan["stages"]:
        if stage["kind"] != "generate":
            continue
        current = read_json(root / "state.json")["stages"].get(stage["id"], {})
        if current.get("status") == "candidate":
            continue
        if current.get("status") in {"running", "unknown", "failed"}:
            break  # Repairs are explicit; timeout never means an automatic retry.
        image_request = reserve_stage(root, stage["id"])
        try:
            candidate = adapter.execute(image_request)
        except Exception:
            record_failure(root, stage["id"], "unknown")
            break  # Do not leak arbitrary provider exception text or credentials.
        if candidate.get("status") == "candidate" and candidate.get("path"):
            import_candidate(root, stage["id"], candidate["path"], simulated=candidate.get("simulated", False),
                             provider_request_id=candidate.get("provider_request_id"), actual_cost=candidate.get("actual_cost"))
        else:
            record_failure(root, stage["id"], "failed" if candidate.get("status") == "failed" else "unknown")
            break
    return read_json(root / "result.json")


def finalize_job(store, image_path, review):
    image_path = _validate_image(image_path)
    _check_private(review)
    with _lock(store) as root:
        state, plan = read_json(root / "state.json"), read_json(root / "plan.json")
        if state["cancelled"] or plan["status"] != "ready":
            raise HappyTripError("PLAN_NOT_READY", "Job is cancelled or plan is not ready")
        for stage in plan["stages"]:
            if stage["kind"] == "generate" and state["stages"].get(stage["id"], {}).get("status") != "candidate":
                raise HappyTripError("STAGE_PENDING", f"Stage {stage['id']} is not complete")
        if state["simulated"]:
            raise HappyTripError("SIMULATED_RESULT", "Mock images cannot become approved photo results")
        if not review.get("reviewer") or review.get("image_sha256") != digest(image_path):
            raise HappyTripError("REVIEW_INVALID", "Review must identify the reviewer and match the exact image SHA-256")
        checks = review.get("checks", [])
        if not checks or review.get("visual_status") not in {"pass", "warn"} or any(c.get("status") not in {"pass", "warn"} for c in checks):
            raise HappyTripError("VALIDATION_FAILED", "All required checks must be reviewed; failed/not_run checks cannot finalize")
        if not REVIEW_CHECKS <= {c.get("name") for c in checks} or any(not c.get("reason") for c in checks):
            raise HappyTripError("REVIEW_INVALID", "Review mode_visual, identity_and_subjects, facts_and_text and edit_scope, with concrete evidence")
        needs_composition = any(s["kind"] == "compose" for s in plan["stages"])
        if needs_composition:
            manifest_path = review.get("composition_manifest")
            if not manifest_path:
                raise HappyTripError("PROVENANCE_MISSING", "This plan requires the compositor's output manifest")
            manifest = read_json(manifest_path)
            if manifest.get("output_sha256") != digest(image_path):
                raise HappyTripError("PROVENANCE_INVALID", "Composition manifest must match the reviewed output")
            if manifest.get("validation", {}).get("status") not in {"pass", "warn"}:
                raise HappyTripError("VALIDATION_FAILED", "Composition checks have not passed")
            source_assets = read_json(root / "assets.json")
            expected_sources = {a["photo_id"]: a for a in source_assets}
            provenance = manifest.get("provenance", [])
            candidate_hashes = {s["sha256"] for s in state["stages"].values() if s.get("sha256")}
            composed_hashes = {p.get("sha256", p.get("candidate_sha256")) for p in provenance
                               if p.get("kind") in {"generated_layer", "overlay", "masked_edit"}
                               or p.get("source_kind") == "supplied_base"}
            if candidate_hashes and not candidate_hashes <= composed_hashes:
                raise HappyTripError("PROVENANCE_INVALID", "Every generated stage candidate must be accounted for in composition")
            if plan["contract"]["scope"] in {"masked_edit", "overlay"}:
                base_record = next((p for p in provenance if p.get("kind") == "base"), {})
                expected = expected_sources.get(base_record.get("photo_id"))
                if not expected or any(base_record.get(k) != expected[k] for k in ("input_sha256", "working_sha256")):
                    raise HappyTripError("PROVENANCE_INVALID", "Local composition base must match this job's registered original")
            if plan["mode"] in {"B01", "B22"}:
                used = {p.get("photo_id") for p in provenance if p.get("kind") == "source_photo"}
                if used != set(expected_sources):
                    raise HappyTripError("PROVENANCE_INVALID", "Composition must use this job's original photos")
                for record in provenance:
                    if record.get("kind") == "source_photo":
                        expected = expected_sources[record["photo_id"]]
                        if any(record.get(k) != expected[k] for k in ("input_sha256", "working_sha256")):
                            raise HappyTripError("PROVENANCE_INVALID", "Source hashes differ from registered job assets")
            if plan["contract"].get("strict_original") and plan["contract"]["scope"] == "masked_edit":
                if not any(c.get("name") == "protected_pixels" and c.get("status") == "pass" and c.get("changed_pixels") == 0
                           for c in manifest.get("checks", [])):
                    raise HappyTripError("PROVENANCE_INVALID", "Strict local edits require a passing protected-pixel comparison")
            if plan["mode"] == "B22":
                if plan["route_layout"].get("template") == "travel_poster":
                    from .planner import route_data_fingerprint
                    if manifest.get("route", {}).get("data_fingerprint") != route_data_fingerprint(plan["route_layout"]):
                        raise HappyTripError("PROVENANCE_INVALID", "Poster facts, map source or route geometry differ from the confirmed plan")
                expected_order = plan["route_layout"]["ordered_stop_ids"]
                if manifest.get("route", {}).get("ordered_stop_ids") != expected_order:
                    raise HappyTripError("PROVENANCE_INVALID", "Route order differs from the confirmed plan")
                expected_mapping = {(s["id"], s["name"], p) for s in plan["route_layout"]["stops"] for p in s["photo_ids"]}
                actual_mapping = {(p.get("stop_id"), p.get("stop_name"), p.get("photo_id")) for p in provenance if p.get("kind") == "source_photo"}
                if expected_mapping != actual_mapping or manifest.get("route", {}).get("edges") != [[a, b] for a, b in zip(expected_order, expected_order[1:])]:
                    raise HappyTripError("PROVENANCE_INVALID", "Route photo mapping or edges differ from the confirmed plan")
            if plan["mode"] == "A07":
                expected_ids = {p["photo_id"] for p in plan.get("asset_mapping", [])}
                mapped_ids = {pid for p in provenance if p.get("kind") == "overlay" for pid in p.get("source_photo_ids", [])}
                if expected_ids != mapped_ids:
                    raise HappyTripError("PROVENANCE_INVALID", "Every selected suitcase photo must appear in a sticker source mapping")
        elif digest(image_path) not in {s.get("sha256") for s in state["stages"].values()}:
            raise HappyTripError("PROVENANCE_INVALID", "Final image must be an imported candidate from this job")
        result = read_json(root / "result.json")
        warned = review["visual_status"] == "warn" or any(c["status"] == "warn" for c in checks)
        result.update(status="completed_with_warning" if warned else "succeeded",
                      image_assets=[{"path": str(image_path), "sha256": digest(image_path)}],
                      validation_status="warn" if warned else "pass")
        result["warnings"] = [c.get("reason", c.get("name", "")) for c in checks if c["status"] == "warn"]
        from .export import export_result
        result["image_assets"] = export_result(result, root / "output")
        write_json(root / "validation.json", review)
        write_json(root / "result.json", result)
        return result
