"""Offline frontend dependency extraction, TypeScript check, and esbuild bundling."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE_DIR = ROOT / "web" / "console"
NODE_MODULES = CONSOLE_DIR / "node_modules"
TSCONFIG = CONSOLE_DIR / "tsconfig.json"
ENTRY = CONSOLE_DIR / "main.tsx"
BUNDLE_OUT = CONSOLE_DIR / "bundle.js"
CSS_OUT = CONSOLE_DIR / "cuberelay_v4.css"
NODE_BIN = Path(os.environ.get("NODE_BIN", "/opt/homebrew/bin/node"))

# Pinned npm tarballs cached locally under ~/.npm/_cacache/content-v2
CACHED_PACKAGES: dict[str, str] = {
    "react": "sha512-wS+hAgJShR0KhEvPJArfuPVN1+Hz1t0Y6n5jLrGQbkb4urgPE/0Rve+1kMB1v/oWgHgm4WIcV+i7F2pTVj+2iQ==",
    "react-dom": "sha512-5m4nQKp+rZRb09LNH59GM4BxTh9251/ylbKIbpe7TpGxfJ+9kv6BLkLBXIjjspbgbnIBNqlI23tRnTWT0snUIw==",
    "scheduler": "sha512-UOShsPwz7NrMUqhR6t0hWjFduvOzbtv7toDH1/hIrfRNIDBnnBWd0CwJTGvTpngVlmwGCdP9/Zl/tVrDqcuYzQ==",
    "loose-envify": "sha512-lyuxPGr/Wfhrlem2CL/UcnUc1zcqKAImBDzukY7Y5F/yQiNdko6+fRLevlw1HgMySw7f611UIY408EtxRSoK3Q==",
    "js-tokens": "sha512-RdJUflcE3cUzKiMqQgsCu06FPu9UdIJO0beYbPhHN4k6apgJtifcoCtT9bcxOpYBtpD2kCM6Sbzg4CausW/PKQ==",
    "lucide-react": "sha512-6koYRhnM2N0GGZIdXzSeiNwguv1gt/FAjZOiPl76roBi3xKEXa4WmfpxgQwTTL4KipXjefrnf3oV4IsYhi4JFA==",
    "typescript": "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==",
    "esbuild": "sha512-bbPBYYrtZbkt6Os6FiTLCTFxvq4tt3JKall1vRwshA3fdVztsLAatFaZobhkBC8/BrPetoa0oksYoKXoG4ryJg==",
    "@esbuild/darwin-arm64": "sha512-N3zl+lxHCifgIlcMUP5016ESkeQjLj/959RxxNYIthIg+CQHInujFuXeWbWMgnTo4cp5XVHqFPmpyu9J65C1Yg==",
    "@types/react": "sha512-vfEqpXTvwT91yhmwdfouStN2hSKwTvyRs8qpLfADyrq/kxDw0hZM7Wk9Ug1FELj8hIby+S/+kQCSRFF32nv2Qw==",
    "@types/react-dom": "sha512-MEe3UeoENYVFXzoXEWsvcpg6ZvlrFNlOQ7EOsvhI3CfAXwzPfO8Qwuxd40nepsYKqyyVQnTdEfv68q91yLcKrQ==",
    "@types/prop-types": "sha512-F6bEyamV9jKGAFBEmlQnesRPGOQqS2+Uwi0Em15xenOxHaf2hv6L8YCVn3rPdPJOiJfPiCnLIRyvwVaqMY3MIw==",
    "csstype": "sha512-z1HGKcYy2xA8AGQfwrn0PAy+PB7X/GSj3UVJW9qKyn43xWa+gl5nXmU4qqLMRzWVLFC8KusUX8T/0kCiOYpAIQ==",
}


def _cacache_path(integrity: str) -> Path:
    if not integrity.startswith("sha512-"):
        raise ValueError(f"Unsupported integrity format: {integrity}")
    digest_hex = base64.b64decode(integrity.split("-", 1)[1]).hex()
    cache_root = Path(os.environ.get("NPM_CACHE_DIR", "~/.npm/_cacache")).expanduser()
    return cache_root / "content-v2" / "sha512" / digest_hex[:2] / digest_hex[2:4] / digest_hex[4:]


def _extract_tarball(pkg_name: str, tgz_path: Path, dest_dir: Path) -> None:
    if not tgz_path.exists():
        raise FileNotFoundError(f"Missing cached tarball for {pkg_name}: {tgz_path}")
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tgz_path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            rel = member.name.lstrip("./")
            if "/" in rel:
                rel = rel.split("/", 1)[1]
            if not rel:
                continue
            target = (dest_dir / rel).resolve()
            if dest_dir.resolve() not in target.parents and target != dest_dir.resolve():
                raise ValueError(f"Unsafe path in tarball {pkg_name}: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            mode = member.mode & 0o777
            if "/bin/" in f"/{rel}" or rel.startswith("bin/"):
                mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            if mode:
                os.chmod(target, mode)


def ensure_node_modules(force: bool = False) -> dict[str, str]:
    extracted: dict[str, str] = {}
    NODE_MODULES.mkdir(parents=True, exist_ok=True)
    for pkg_name, integrity in CACHED_PACKAGES.items():
        pkg_dir = NODE_MODULES / pkg_name
        pkg_json = pkg_dir / "package.json"
        if force or not pkg_json.exists():
            tgz = _cacache_path(integrity)
            _extract_tarball(pkg_name, tgz, pkg_dir)
            extracted[pkg_name] = str(tgz)
        else:
            extracted[pkg_name] = "cached"
    # Ensure esbuild binary is executable
    esbuild_bin = NODE_MODULES / "@esbuild" / "darwin-arm64" / "bin" / "esbuild"
    if esbuild_bin.exists():
        os.chmod(esbuild_bin, esbuild_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return extracted


def run_typecheck() -> None:
    tsc_js = NODE_MODULES / "typescript" / "lib" / "tsc.js"
    cmd = [str(NODE_BIN), str(tsc_js), "-p", str(TSCONFIG), "--noEmit"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"TypeScript typecheck failed (exit {proc.returncode}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def run_bundle() -> None:
    esbuild_bin = NODE_MODULES / "@esbuild" / "darwin-arm64" / "bin" / "esbuild"
    if not esbuild_bin.exists():
        esbuild_js = NODE_MODULES / "esbuild" / "bin" / "esbuild"
        cmd = [str(NODE_BIN), str(esbuild_js)]
    else:
        cmd = [str(esbuild_bin)]
    cmd.extend(
        [
            str(ENTRY),
            "--bundle",
            f"--outfile={BUNDLE_OUT}",
            "--format=iife",
            "--platform=browser",
            "--target=es2020",
            "--jsx=automatic",
            "--define:process.env.NODE_ENV=\"production\"",
        ]
    )
    env = dict(os.environ)
    env["NODE_PATH"] = str(NODE_MODULES)
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"esbuild failed (exit {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    if not BUNDLE_OUT.exists() or BUNDLE_OUT.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty bundle at {BUNDLE_OUT}")
    if not CSS_OUT.exists() or CSS_OUT.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty stylesheet at {CSS_OUT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CubeRelay M3-D console offline.")
    parser.add_argument("--typecheck", action="store_true", help="Run tsc --noEmit before bundling.")
    parser.add_argument("--force-extract", action="store_true", help="Re-extract offline npm packages.")
    args = parser.parse_args()

    pkgs = ensure_node_modules(force=args.force_extract)
    if args.typecheck:
        run_typecheck()
    run_bundle()

    summary = {
        "ok": True,
        "typechecked": bool(args.typecheck),
        "bundle_path": str(BUNDLE_OUT),
        "bundle_bytes": BUNDLE_OUT.stat().st_size,
        "css_path": str(CSS_OUT),
        "css_bytes": CSS_OUT.stat().st_size,
        "packages_count": len(pkgs),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
