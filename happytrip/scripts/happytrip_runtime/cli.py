import argparse
import json
from pathlib import Path
import platform
import sys

from .types import HappyTripError


def parser():
    p = argparse.ArgumentParser(description="HappyTrip local planning and native-image-tool handoff")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog", help="List all 18 supported modes")
    sub.add_parser("doctor", help="Inspect local dependencies; does not infer host image capabilities")
    for name in ("prepare", "run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--request", required=True)
        cmd.add_argument("--job-dir", required=True)
        if name == "run":
            cmd.add_argument("--adapter", choices=["mock"], required=True)
    for name in ("reserve", "import", "record-failure"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--job-dir", required=True)
        cmd.add_argument("--stage", required=True)
        if name == "import":
            cmd.add_argument("--image", required=True)
            cmd.add_argument("--provider-request-id")
        if name == "record-failure":
            cmd.add_argument("--status", choices=["failed", "unknown"], required=True)
    cmd = sub.add_parser("cancel")
    cmd.add_argument("--job-dir", required=True)
    cmd = sub.add_parser("finalize")
    cmd.add_argument("--job-dir", required=True)
    cmd.add_argument("--image", required=True)
    cmd.add_argument("--review", required=True)
    cmd = sub.add_parser("compose")
    cmd.add_argument("--recipe", required=True)
    cmd.add_argument("--output", required=True)
    cmd = sub.add_parser("map-basemap", help="Register a local Mercator raster or render sourced WGS84 GeoJSON; no network")
    source = cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--image")
    source.add_argument("--geojson")
    cmd.add_argument("--bounds", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    cmd.add_argument("--source", required=True)
    cmd.add_argument("--attribution", required=True)
    cmd.add_argument("--output", required=True)
    cmd.add_argument("--size", nargs=2, type=int, default=[1400, 1000])
    cmd.add_argument("--font-path")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            import PIL
            result = {"python": platform.python_version(), "pillow": PIL.__version__,
                      "local_helpers": True, "native_image_tool": "must be confirmed from host tools",
                      "network_client": False, "visual_validation": "not_run",
                      "route_poster": True, "geographic_rendering": "local attributed Mercator raster or WGS84 GeoJSON",
                      "route_navigation": False}
        elif args.command == "catalog":
            from .catalog import load_catalog
            catalog = load_catalog()
            result = [{k: m[k] for k in ("id", "name_zh", "category", "edit_scope", "validation_priority")}
                      for m in catalog["modes"]]
        elif args.command == "map-basemap":
            from .maps import create_basemap
            result = create_basemap(output=args.output, bounds=args.bounds, source=args.source,
                                    attribution=args.attribution, image_path=args.image,
                                    geojson_path=args.geojson, size=args.size, font_path=args.font_path)
        elif args.command == "compose":
            from .compositor import compose
            from .runner import read_json, write_json
            recipe = read_json(args.recipe)
            layout = {**recipe.get("layout", {}), "output_path": str(Path(args.output).resolve())}
            result = compose(recipe.get("base"), recipe.get("layers", []), layout, recipe.get("contract", {}))
            write_json(str(Path(args.output).resolve()) + ".json", result)
        else:
            from . import runner
            if args.command in {"prepare", "run"}:
                request = runner.read_json(args.request)
                if args.command == "run":
                    from .adapters.mock import MockAdapter
                    result = runner.run_job(request, MockAdapter(), args.job_dir)
                else:
                    from .adapters.host import HostAdapter
                    result = runner.prepare_job(request, HostAdapter(request.get("capabilities")), args.job_dir)
            elif args.command == "reserve":
                result = runner.reserve_stage(args.job_dir, args.stage)
            elif args.command == "import":
                result = runner.import_candidate(args.job_dir, args.stage, args.image,
                                                 provider_request_id=args.provider_request_id)
            elif args.command == "record-failure":
                result = runner.record_failure(args.job_dir, args.stage, args.status)
            elif args.command == "cancel":
                result = runner.cancel_job(args.job_dir)
            else:
                result = runner.finalize_job(args.job_dir, args.image, runner.read_json(args.review))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except HappyTripError as exc:
        print(json.dumps({"status": "failed", "error": {"code": exc.code, "message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Avoid dumping user input or arbitrary path/provider content in traceback.
        print(json.dumps({"status": "failed", "error": {"code": "INVALID_INPUT", "message": type(exc).__name__}}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
