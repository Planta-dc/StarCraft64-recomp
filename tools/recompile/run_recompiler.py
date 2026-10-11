#!/usr/bin/env python3
"""Run N64Recomp with transactional output and reject its zero-exit failures.

The pinned CLI can return status zero after failing to recompile a function.
A success is therefore accepted only after checking diagnostics and complete
required artifacts. A failed rerun never replaces a previous valid output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def inspect_output(directory: Path, log: str) -> dict:
    failure = re.search(r"(?im)^.*(?:Unhandled |Error |Failed |No function found).*$", log)
    if failure:
        raise ValueError(f"Recompiler diagnostic rejected: {failure.group(0)}")
    required = [directory / "funcs.h", directory / "recomp_overlays.inl", directory / "lookup.cpp"]
    functions = sorted(directory.glob("funcs_*.c"))
    if not functions or any(not path.is_file() or not path.stat().st_size for path in required + functions):
        raise ValueError("Recompiler output is incomplete")
    if "RECOMP_FUNC void recomp_entrypoint(" not in "\n".join(path.read_text() for path in functions):
        raise ValueError("Entrypoint was not emitted")
    if "static SectionTableEntry section_table[]" not in required[1].read_text():
        raise ValueError("Section registration table was not emitted")
    files = sorted(path for path in directory.iterdir() if path.is_file())
    return {"function_source_files": len(functions), "files": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "warnings": [line for line in log.splitlines() if line.startswith(("[Warn]", "[Info]"))]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--recompiler", type=Path, default=Path("local/build/recompiler/N64Recomp"))
    parser.add_argument("--output", type=Path, default=Path("local/generated/game"))
    parser.add_argument("--replace", action="store_true", help="Replace a previous private generated output after success")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if not output.is_relative_to(root / "local"):
        raise SystemExit("Generated output must remain under ignored local/")
    if output.exists() and not args.replace:
        raise SystemExit("Output already exists; pass --replace for a transactional successful replacement")
    config = args.config.resolve()
    text = config.read_text()
    work = Path(tempfile.mkdtemp(prefix="recompile-", dir=config.parent))
    temporary_output = work / "generated"
    config_text, count = re.subn(r'(?m)^output_func_path\s*=\s*[^\n]+$',
                               lambda _: "output_func_path = " + json.dumps(str(temporary_output)), text)
    if count != 1:
        raise SystemExit("Expected one output_func_path in the generated config")
    # Keep the temporary config next to the original so relative symbol paths
    # retain their meaning. Preserve the scratch directory on every failure.
    temporary_config = config.parent / (work.name + ".toml")
    temporary_config.write_text(config_text)
    with (work / "recompiler.log").open("w") as log_file:
        result = subprocess.run([str(args.recompiler.resolve()), str(temporary_config)],
                                stdout=log_file, stderr=subprocess.STDOUT)
    log = (work / "recompiler.log").read_text()
    if result.returncode:
        raise SystemExit(f"Recompiler exited {result.returncode}; diagnostics: {work / 'recompiler.log'}")
    try:
        report = inspect_output(temporary_output, log)
    except ValueError as error:
        raise SystemExit(f"{error}; diagnostics: {work / 'recompiler.log'}") from error
    report["config_sha256"] = hashlib.sha256(config.read_bytes()).hexdigest()
    report["recompiler_sha256"] = hashlib.sha256(args.recompiler.read_bytes()).hexdigest()
    (work / "generation.json").write_text(json.dumps(report, indent=2) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.rename(work / "previous-output")
    try:
        temporary_output.rename(output)
    except BaseException:
        if (work / "previous-output").exists():
            (work / "previous-output").rename(output)
        raise
    temporary_config.unlink()
    print(f"PASS: {len(report['files'])} generated files; report {work / 'generation.json'}")


if __name__ == "__main__":
    main()
