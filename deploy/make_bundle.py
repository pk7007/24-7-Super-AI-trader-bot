"""Create a credential-free deployment bundle; state requires both bots to be stopped."""

from __future__ import annotations

import argparse
import os
import tarfile
from contextlib import ExitStack, contextmanager
from pathlib import Path

ITEMS = ("bot", "tests", "requirements.txt", "requirements.lock", "Dockerfile", "docker-compose.yml",
         ".dockerignore", "SAFETY_RULES.md", "DEPLOYMENT.md", "KNOWN_LIMITATIONS.md", "deploy/setup_vps.sh",
         "deploy/make_bundle.py", "deploy/make_bundle.sh")


@contextmanager
def state_locks(root: Path):
    """Use the same exclusive locks as bot.main; keep them until tar has finished reading state."""
    with ExitStack() as stack:
        for mode in ("paper", "shadow"):
            directory = root / "state" / mode
            if not directory.is_dir():
                raise FileNotFoundError(f"missing {mode} state directory")
            handle = stack.enter_context((directory / "bot.lock").open("a+b"))
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError(f"{mode} bot is running; stop it and disable its restarts before bundling state") from exc
        yield


def _safe_member(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = Path(info.name).parts
    if (info.issym() or info.islnk() or any(part.startswith(".env") or part == "__pycache__" for part in parts)
            or info.name.endswith((".tmp", ".pyc"))
            or (info.name.endswith(".lock") and parts[-1] != "requirements.lock")):
        return None
    return info


def create_bundle(root: Path, *, with_state: bool = False) -> Path:
    root = Path(root).resolve()
    output = root / "deploy" / "bundle.tar.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    with ExitStack() as stack:
        if with_state:
            stack.enter_context(state_locks(root))
        items = list(ITEMS)
        for name in items:
            if not (root / name).exists() or (root / name).is_symlink():
                raise FileNotFoundError(f"required bundle input missing or symlinked: {name}")
        if with_state:
            items += ["state/paper", "state/shadow"]
        try:
            with tarfile.open(temporary, "w:gz") as archive:
                for name in items:
                    archive.add(root / name, arcname=f"{root.name}/{name}", filter=_safe_member)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-state", action="store_true")
    args = parser.parse_args()
    print(create_bundle(Path(__file__).resolve().parent.parent, with_state=args.with_state))


if __name__ == "__main__":
    main()
