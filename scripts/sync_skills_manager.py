"""Verify both file trees before refreshing the local Skills Manager installation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


SKILL = "delegated-execution-protocol"


def revision_files(root, revision):
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", revision + "^{commit}"], cwd=root
    ).strip().decode("ascii")
    tree = subprocess.check_output(["git", "ls-tree", "-rz", commit], cwd=root)
    entries = {}
    for item in tree.split(b"\0"):
        if item:
            header, path = item.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split()
            if kind != "blob":
                raise ValueError(f"unsupported Git entry: {os.fsdecode(path)!r}")
            entries[os.fsdecode(path)] = mode, oid
    return entries


def check_tree(root, expected, label, *, checkout=False):
    seen = set()
    differences = []

    def visit(directory):
        for path in directory.iterdir():
            if checkout and directory == root and path.name == ".git":
                continue
            name = str(path.relative_to(root))
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                visit(path)
                continue
            seen.add(name)
            if name not in expected:
                differences.append((name, "多出"))
                continue
            want_mode, oid = expected[name]
            if stat.S_ISLNK(mode):
                data = os.fsencode(os.readlink(path))
                actual_mode = "120000"
            elif stat.S_ISREG(mode):
                data = path.read_bytes()
                actual_mode = "100755" if mode & stat.S_IXUSR else "100644"
            else:
                differences.append((name, "文件类型不同"))
                continue
            digest = hashlib.new("sha1" if len(oid) == 40 else "sha256")
            digest.update(f"blob {len(data)}\0".encode())
            digest.update(data)
            if digest.hexdigest() != oid:
                differences.append((name, "内容不同"))
            if actual_mode != want_mode:
                differences.append((name, "文件类型或执行权限不同"))

    visit(root)
    differences.extend((name, "缺少") for name in expected.keys() - seen)
    for name, reason in sorted(differences):
        print(f"{label} {reason} {json.dumps(name, ensure_ascii=False)}", file=sys.stderr)
    return not differences


def sync(root, manager, baseline, check_only=False):
    def call(action):
        return json.loads(subprocess.check_output([manager, "--json", "skills", action, SKILL]))

    info = call("show")
    library = Path(info["path"]).resolve(strict=True)
    if info["source_type"] != "local" or Path(info["source_ref"]).resolve() != root or library == root:
        raise ValueError("Skills Manager registration does not match this local source")
    candidate = revision_files(root, "HEAD")
    library_ok = check_tree(library, revision_files(root, baseline), "Manager")
    source_ok = check_tree(root, candidate, "源码", checkout=True)
    if not (library_ok and source_ok):
        return 1
    if not check_only:
        updates = call("update")
        if not any(item.get("refreshed") is True and not item.get("error") for item in updates):
            raise ValueError("Skills Manager did not confirm the refresh")
        if not check_tree(library, candidate, "更新后的 Manager"):
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Last verified synchronized source commit")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--manager-cli", type=Path)
    args = parser.parse_args()
    bridge = Path.home() / ".skills-manager/bin/skills-manager-cli"
    manager = args.manager_cli or (bridge if bridge.exists() else shutil.which("skills-manager-cli"))
    if not manager:
        parser.exit(1, "Skills Manager CLI unavailable\n")
    try:
        return sync(Path(__file__).resolve().parents[1], manager, args.baseline, args.check_only)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Skills Manager sync failed: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
