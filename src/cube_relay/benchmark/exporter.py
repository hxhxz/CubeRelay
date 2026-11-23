"""Serializable JSON/JSONL/Markdown/ZIP exporter and integrity verifier for M4-D Benchmark."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any
import zipfile

from cube_relay.experiment.recorder import _current_git_commit, redact_secrets

from .schema import (
    BENCHMARK_VERSION,
    BenchmarkCase,
    BenchmarkRunResult,
    DecisionRecord,
    utc_now_iso,
)

_SECRET_PATTERN = re.compile(r"(AIza[0-9A-Za-z\-_]{20,}|sk-[0-9A-Za-z]{16,}|Bearer\s+[0-9A-Za-z\-_\.]{16,})")
_TELEMETRY_TOKEN_KEYS = {"token_usage", "token_summary", "input_tokens", "output_tokens", "total_tokens"}


def _sanitize_benchmark_payload(payload: Any, *, key_name: str | None = None) -> Any:
    """Redact secrets and sensitive keys while preserving numeric token-count telemetry."""
    if key_name in _TELEMETRY_TOKEN_KEYS:
        if isinstance(payload, (int, float)):
            return payload
        if isinstance(payload, dict) and all(isinstance(v, (int, float)) for v in payload.values()):
            return dict(payload)
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            ks = str(k)
            if ks not in _TELEMETRY_TOKEN_KEYS and any(w in ks.lower() for w in ("api_key", "secret", "password", "auth", "credential")):
                out[ks] = "<REDACTED>"
            else:
                out[ks] = _sanitize_benchmark_payload(v, key_name=ks)
        return out
    if isinstance(payload, list):
        return [_sanitize_benchmark_payload(item) for item in payload]
    if isinstance(payload, str):
        cleaned = redact_secrets(payload)
        return _SECRET_PATTERN.sub("<REDACTED>", str(cleaned))
    return redact_secrets(payload)


def _dump_jsonl_bytes(items: list[Any]) -> bytes:
    lines: list[str] = []
    for item in items:
        raw = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        sanitized = _sanitize_benchmark_payload(raw)
        lines.append(json.dumps(sanitized, ensure_ascii=False))
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _dump_json_bytes(payload: Any) -> bytes:
    raw = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    sanitized = _sanitize_benchmark_payload(raw)
    return (json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def verify_reference_integrity(
    *,
    result: BenchmarkRunResult,
    cases: list[BenchmarkCase] | None = None,
) -> dict[str, Any]:
    """Verify causal/reference integrity and strict Fake Provider segregation in BenchmarkRunResult."""
    broken: list[dict[str, str]] = []
    case_ids = {c.case_id for c in (cases or [])}

    for rec in [*result.decision_records, *result.vlm_ablation_records, *result.guide_ablation_records]:
        if case_ids and rec.benchmark_case_id not in case_ids:
            broken.append({
                "table": "decision_records",
                "id": rec.record_id,
                "missing_ref": f"case:{rec.benchmark_case_id}",
            })

    # Verify Fake segregation invariant: no scorecard in real_scorecards has is_fake_provider=True
    for key, sc in result.real_scorecards.items():
        if sc.is_fake_provider or sc.included_in_real_agent_ranking is False:
            broken.append({
                "table": "real_scorecards",
                "id": key,
                "missing_ref": "FAKE_PROVIDER_CONTAMINATED_REAL_SCORECARD",
            })

    # Verify forbidden VLM condition never executed in MuJoCo closed loop
    for ep in result.closed_loop_episodes:
        notes_upper = str(ep.setup_notes or "").upper()
        if "VLM_SWAPPED" in notes_upper or "VLM_CONTRADICTORY" in notes_upper:
            broken.append({
                "table": "closed_loop_episodes",
                "id": ep.episode_id,
                "missing_ref": "FORBIDDEN_VLM_CONDITION_IN_CLOSED_LOOP",
            })

    return {
        "ok": len(broken) == 0,
        "broken_count": len(broken),
        "broken": broken,
        "checked_records": len(result.decision_records) + len(result.vlm_ablation_records) + len(result.guide_ablation_records),
        "checked_cases": len(case_ids),
    }


def verify_benchmark_zip_integrity(zip_path: str | Path) -> dict[str, Any]:
    """Inspect a Benchmark ZIP package and verify SHA-256, sizes, redaction, and invariants."""
    zp = Path(zip_path).resolve()
    if not zp.exists():
        raise FileNotFoundError(f"Benchmark ZIP not found: {zp}")

    mismatches: list[str] = []
    secret_hits: list[str] = []
    with zipfile.ZipFile(zp, mode="r") as zf:
        if "manifest.json" not in zf.namelist():
            return {"ok": False, "error": "MISSING_MANIFEST", "mismatches": ["manifest.json"]}
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        for entry in manifest.get("files", []):
            rel = str(entry["path"])
            if rel not in zf.namelist():
                mismatches.append(f"missing:{rel}")
                continue
            raw = zf.read(rel)
            sha = hashlib.sha256(raw).hexdigest()
            if sha != entry.get("sha256"):
                mismatches.append(f"sha256_mismatch:{rel}")
            if len(raw) != int(entry.get("size_bytes", -1)):
                mismatches.append(f"size_mismatch:{rel}")
            text = raw.decode("utf-8", errors="ignore")
            if _SECRET_PATTERN.search(text):
                secret_hits.append(rel)

        result = BenchmarkRunResult.model_validate(json.loads(zf.read("summary.json").decode("utf-8")))
        cases = (
            [BenchmarkCase.model_validate(c) for c in json.loads(zf.read("cases.json").decode("utf-8"))]
            if "cases.json" in zf.namelist()
            else None
        )
        ref_check = verify_reference_integrity(result=result, cases=cases)

    return {
        "ok": (len(mismatches) == 0 and len(secret_hits) == 0 and bool(ref_check["ok"])),
        "manifest_files_checked": len(manifest.get("files", [])),
        "mismatches": mismatches,
        "secret_hits": secret_hits,
        "reference_integrity": ref_check,
        "benchmark_run_id": result.benchmark_run_id,
    }


class BenchmarkExporter:
    """Writes M4-D Benchmark run directories and verifiable ZIP exports."""

    @staticmethod
    def build_markdown_report(
        result: BenchmarkRunResult,
        *,
        cases: list[BenchmarkCase] | None = None,
    ) -> str:
        lines: list[str] = [
            f"# CubeRelay M4-D Benchmark Run Report (`{result.benchmark_run_id}`)",
            "",
            f"- **Benchmark Version**: `{result.benchmark_version}`",
            f"- **Execution Mode**: `{result.execution_mode}`",
            f"- **Contains Fake Provider**: `{result.contains_fake_provider}`",
            f"- **Generated UTC**: `{result.generated_utc}`",
            f"- **Decision Records**: `{len(result.decision_records)}` | **VLM Ablation**: `{len(result.vlm_ablation_records)}` | **Guide Ablation**: `{len(result.guide_ablation_records)}` | **Closed-Loop Episodes**: `{len(result.closed_loop_episodes)}`",
            "",
        ]
        if cases is not None:
            lines.append(f"- **Benchmark Cases Loaded**: `{len(cases)}`")
            lines.append("")

        def _fmt_metric(m: Any) -> str:
            if m is None or m.value is None:
                return "N/A"
            ci = ""
            if m.ci_95_low is not None and m.ci_95_high is not None:
                ci = f" (95% CI [{m.ci_95_low:.2f}, {m.ci_95_high:.2f}])"
            return f"{m.value * 100:.1f}% ({m.numerator}/{m.denominator}){ci}"

        def _append_scorecards_section(title: str, cards: dict[str, Any]) -> None:
            lines.extend([f"## {title}", ""])
            if not cards:
                lines.extend(["*None*", ""])
                return
            lines.append("| Group Label | Source | Legal | Schema | Appropriate | Forbidden | L1 | L2 | L3 | L4 | L5 | Latency(ms) |")
            lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for key, sc in cards.items():
                dm = sc.decision_metrics
                pd = sc.per_dimension
                def _dim_pct(dname: str) -> str:
                    ds = pd.get(dname)
                    if ds is None or ds.pass_rate.value is None:
                        return "N/A"
                    return f"{ds.pass_rate.value * 100:.0f}% ({ds.passed_count}/{ds.pass_rate.denominator})"
                lat = sc.latency_summary_ms.get("mean_ms")
                lat_s = f"{lat:.0f}" if lat is not None else "N/A"
                lines.append(
                    f"| `{key}` | `{sc.execution_source_label.value}` "
                    f"| {_fmt_metric(dm.get('legal_action_rate'))} "
                    f"| {_fmt_metric(dm.get('schema_validity_rate'))} "
                    f"| {_fmt_metric(dm.get('decision_appropriateness_rate'))} "
                    f"| {_fmt_metric(dm.get('forbidden_action_rate'))} "
                    f"| {_dim_pct('L1_SKILL_SELECTION')} "
                    f"| {_dim_pct('L2_STATE_AWARE_PLANNING')} "
                    f"| {_dim_pct('L3_PERCEPTION_GROUNDED_REASONING')} "
                    f"| {_dim_pct('L4_FAILURE_RECOVERY')} "
                    f"| {_dim_pct('L5_GENERALIZATION')} "
                    f"| {lat_s} |"
                )
            lines.append("")

        _append_scorecards_section("Real / Baseline Scorecards (Included in Real Comparison)", result.real_scorecards)
        if result.fake_validation_scorecards:
            _append_scorecards_section(
                "Fake Provider Framework Validation Scorecards (EXCLUDED FROM REAL AGENT RANKING)",
                result.fake_validation_scorecards,
            )

        if result.vlm_ablation_summary:
            lines.extend(["## L3 VLM Semantic Causal Ablation", ""])
            by_cond = result.vlm_ablation_summary.get("by_condition") or result.vlm_ablation_summary.get("fake_only", {}).get("by_condition") or {}
            if by_cond:
                lines.append("| VLM Condition | N | Comparable | Pass | Accuracy | Forbidden Rate | Evidence Grounding |")
                lines.append("|---|---:|---:|---:|---:|---:|---:|")
                for cond, stats in by_cond.items():
                    acc = stats.get("accuracy", {})
                    forb = stats.get("forbidden_rate", {})
                    ev = stats.get("evidence_grounding_rate", {})
                    acc_s = f"{acc['value']*100:.1f}%" if acc.get("value") is not None else "N/A"
                    forb_s = f"{forb['value']*100:.1f}%" if forb.get("value") is not None else "N/A"
                    ev_s = f"{ev['value']*100:.1f}%" if ev.get("value") is not None else "N/A"
                    lines.append(
                        f"| `{cond}` | {stats.get('n', 0)} | {stats.get('comparable_n', 0)} | {stats.get('passed', 0)} | {acc_s} | {forb_s} | {ev_s} |"
                    )
                lines.append("")

        if result.guide_ablation_summary:
            lines.extend(["## Prompt Guide Ablation (`GUIDE_FULL` vs `GUIDE_MINIMAL`)", ""])
            lines.append("| Planner Group | GUIDE_FULL N | GUIDE_FULL Acc | GUIDE_MINIMAL N | GUIDE_MINIMAL Acc | Delta (MIN - FULL) |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for grp, st in result.guide_ablation_summary.items():
                lines.append(
                    f"| `{grp}` | {st['guide_full_n']} | {st['guide_full_acc']*100:.1f}% "
                    f"| {st['guide_minimal_n']} | {st['guide_minimal_acc']*100:.1f}% "
                    f"| {st['delta_minimal_minus_full']*100:+.1f}% |"
                )
            lines.append("")

        if result.closed_loop_episodes:
            lines.extend(["## Layer B: Closed-Loop MuJoCo Episodes", ""])
            lines.append("| Episode | Scenario | Group | Guide | Status | Goal Achieved | Attribution | Skills | Wall(s) |")
            lines.append("|---|---|---|---|---|---|---|---|---:|")
            for ep in result.closed_loop_episodes:
                lines.append(
                    f"| `{ep.episode_id}` | `{ep.scenario_id}` | `{ep.planner_group.value}` | `{ep.guide_mode.value}` "
                    f"| `{ep.mission_status}` | `{ep.goal_achieved}` | `{ep.failure_attribution.primary_category.value}` "
                    f"| `{' -> '.join(ep.skills_executed)}` | {ep.wall_time_s:.2f} |"
                )
            lines.append("")

        if result.incomparabilities:
            lines.extend(["## Explicit Incomparabilities", ""])
            for item in result.incomparabilities:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def write_run_directory(
        result: BenchmarkRunResult,
        *,
        out_dir: str | Path,
        cases: list[BenchmarkCase] | None = None,
        export_zip: bool = True,
    ) -> dict[str, Path]:
        """Write benchmark artifacts to a directory (and optional verified ZIP archive)."""
        dest = Path(out_dir).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}

        if cases is not None:
            p = dest / "cases.json"
            # Do NOT leak base64 images redundantly if massive? Keep full serializable cases!
            p.write_bytes(_dump_json_bytes([c.model_dump(mode="json") for c in cases]))
            written["cases"] = p

        for name, rows in [
            ("decision_records.jsonl", result.decision_records),
            ("vlm_ablation.jsonl", result.vlm_ablation_records),
            ("guide_ablation.jsonl", result.guide_ablation_records),
        ]:
            p = dest / name
            p.write_bytes(_dump_jsonl_bytes(rows))
            written[name] = p

        cl_path = dest / "closed_loop_episodes.json"
        cl_path.write_bytes(_dump_json_bytes([ep.model_dump(mode="json") for ep in result.closed_loop_episodes]))
        written["closed_loop_episodes"] = cl_path

        sc_payload = {
            "benchmark_run_id": result.benchmark_run_id,
            "contains_fake_provider": result.contains_fake_provider,
            "real_scorecards": {k: v.model_dump(mode="json") for k, v in result.real_scorecards.items()},
            "fake_validation_scorecards": {k: v.model_dump(mode="json") for k, v in result.fake_validation_scorecards.items()},
        }
        sc_path = dest / "scorecards.json"
        sc_path.write_bytes(_dump_json_bytes(sc_payload))
        written["scorecards"] = sc_path

        sum_path = dest / "summary.json"
        sum_path.write_bytes(_dump_json_bytes(result))
        written["summary"] = sum_path

        report_md = BenchmarkExporter.build_markdown_report(result, cases=cases)
        rep_path = dest / "report.md"
        rep_path.write_text(report_md, encoding="utf-8")
        written["report"] = rep_path

        if export_zip:
            zip_path = dest / f"benchmark_{result.benchmark_run_id}.zip"
            _, _ = BenchmarkExporter.export_zip_bytes(result, cases=cases, out_path=zip_path)
            written["zip"] = zip_path

        return written

    @staticmethod
    def export_zip_bytes(
        result: BenchmarkRunResult,
        *,
        cases: list[BenchmarkCase] | None = None,
        out_path: str | Path | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        """Bundle benchmark run artifacts into a verifiable SHA-256 signed ZIP archive."""
        entries: dict[str, bytes] = {
            "summary.json": _dump_json_bytes(result),
            "decision_records.jsonl": _dump_jsonl_bytes(result.decision_records),
            "vlm_ablation.jsonl": _dump_jsonl_bytes(result.vlm_ablation_records),
            "guide_ablation.jsonl": _dump_jsonl_bytes(result.guide_ablation_records),
            "closed_loop_episodes.json": _dump_json_bytes([ep.model_dump(mode="json") for ep in result.closed_loop_episodes]),
            "scorecards.json": _dump_json_bytes({
                "real_scorecards": {k: v.model_dump(mode="json") for k, v in result.real_scorecards.items()},
                "fake_validation_scorecards": {k: v.model_dump(mode="json") for k, v in result.fake_validation_scorecards.items()},
            }),
            "report.md": BenchmarkExporter.build_markdown_report(result, cases=cases).encode("utf-8"),
        }
        if cases is not None:
            entries["cases.json"] = _dump_json_bytes([c.model_dump(mode="json") for c in cases])

        ref_integrity = verify_reference_integrity(result=result, cases=cases)
        manifest_files = []
        for rel_path in sorted(entries):
            raw = entries[rel_path]
            manifest_files.append({
                "path": rel_path,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })

        manifest = {
            "benchmark_version": BENCHMARK_VERSION,
            "benchmark_run_id": result.benchmark_run_id,
            "execution_mode": result.execution_mode,
            "contains_fake_provider": result.contains_fake_provider,
            "generated_utc": utc_now_iso(),
            "git_commit": _current_git_commit(),
            "reference_integrity": ref_integrity,
            "files": manifest_files,
        }
        entries["manifest.json"] = json.dumps(redact_secrets(manifest), indent=2, ensure_ascii=False).encode("utf-8")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel_path in sorted(entries):
                zf.writestr(rel_path, entries[rel_path])
        zip_bytes = buf.getvalue()
        if out_path is not None:
            dest = Path(out_path).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zip_bytes)
        return zip_bytes, manifest


def load_benchmark_run(path: str | Path) -> BenchmarkRunResult:
    """Load a BenchmarkRunResult from a run directory, summary.json, or exported ZIP."""
    p = Path(path).resolve()
    if p.is_dir():
        summary_file = p / "summary.json"
        if not summary_file.exists():
            raise FileNotFoundError(f"summary.json not found in {p}")
        return BenchmarkRunResult.model_validate(json.loads(summary_file.read_text(encoding="utf-8")))
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p, mode="r") as zf:
            if "summary.json" not in zf.namelist():
                raise FileNotFoundError(f"summary.json missing inside ZIP {p}")
            return BenchmarkRunResult.model_validate(json.loads(zf.read("summary.json").decode("utf-8")))
    return BenchmarkRunResult.model_validate(json.loads(p.read_text(encoding="utf-8")))


def discover_benchmark_runs(root_dir: str | Path) -> list[dict[str, Any]]:
    """Discover saved benchmark summary.json runs under root_dir, sorted newest first."""
    base = Path(root_dir).resolve()
    if not base.exists():
        return []
    found: list[dict[str, Any]] = []
    candidates: list[Path] = []
    if (base / "summary.json").exists():
        candidates.append(base / "summary.json")
    for sub in sorted(base.iterdir(), reverse=True):
        if sub.is_dir() and (sub / "summary.json").exists():
            candidates.append(sub / "summary.json")
    seen_ids: set[str] = set()
    for sf in candidates:
        try:
            payload = json.loads(sf.read_text(encoding="utf-8"))
            rid = str(payload.get("benchmark_run_id") or "")
            if rid and rid in seen_ids:
                continue
            seen_ids.add(rid)
            found.append({
                "benchmark_run_id": rid,
                "execution_mode": payload.get("execution_mode"),
                "contains_fake_provider": bool(payload.get("contains_fake_provider", False)),
                "generated_utc": payload.get("generated_utc"),
                "decision_count": len(payload.get("decision_records") or []),
                "vlm_ablation_count": len(payload.get("vlm_ablation_records") or []),
                "closed_loop_count": len(payload.get("closed_loop_episodes") or []),
                "summary_path": str(sf),
                "run_dir": str(sf.parent),
            })
        except Exception:
            continue
    return sorted(found, key=lambda x: str(x.get("generated_utc") or ""), reverse=True)
