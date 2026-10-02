# HappyTrip implementation contract

Original documents in `HappyTrip_V1_Package/` are preserved. The deliverable is
the self-contained `happytrip/` skill. Runtime modules live in
`happytrip/scripts/happytrip_runtime`; use `PYTHONPATH=happytrip/scripts` for tests.

All public records are JSON-native dictionaries (see types.py). Raise
`HappyTripError(code, message)` for validation errors. Paths are strings.

- Asset: photo_id, ref (original absolute path), working_path, roles, width,
  height, orientation_normalized, input_sha256, working_sha256.
- Catalog: original JSON plus `_root` absolute skill directory. Mode: original
  mode dictionary plus `template_path` absolute mode-card path.
- Recommendation: mode, reason. `recommend(request, assets, catalog)`.
- `make_plan(request, assets, mode, caps)` returns mode, status, errors (code,
  message), warnings, contract, stages, required_inputs, required_capabilities,
  call_budget (max_image_calls, max_repairs_per_stage), estimated_image_calls.
- Stage: id, kind (`generate`, `compose`, `validate`), photo_ids,
  depends_on (stage IDs), instruction, image_calls (0 or 1), unit.
- `resolve_assets(request, resolver=None, workdir=None)` resolves local refs or
  resolver(ref), writes sanitized copies to workdir, returns Asset list.
- `compile_prompt(mode, context)` where context is the eight template variables;
  `build_context(request, assets, plan)` produces them. Never read all modes.
- Adapter: capabilities() returns dict; execute(image_request) returns dict:
  status (`candidate`, `failed`, `unknown`, `prompt_only`), path (optional real
  file), provider_request_id, error, simulated (bool), actual_cost (optional).
  ImageRequest: mode, stage_id, prompt, references (absolute paths),
  output_dir, idempotency_key. Host handoff prepares requests and imports files;
  Python does not invent tool APIs or automatically call external services.
- Compositor functions explicitly called by CLI; runner does not guess layouts.
  `verify_protected_pixels(before, after, effective_mask)` returns status,
  reason and changed_pixels; decoded normalized image comparison, PNG master.
- `run_job(request, adapter, store)` prepares plan/prompts and invokes only
  adapter generation stages, checkpoints every call. Composition/visual review
  pending yields candidate records, never succeeded. Host return is prompt_only
  until actual results imported. Mock is always simulated and not visual proof.

Scope: deterministic support plus native host instructions. Real photo acceptance
for all 18 modes is separate and remains not_run until performed.
