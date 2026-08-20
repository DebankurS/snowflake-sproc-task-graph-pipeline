"""
Registers each procedures/<name>/ node as a permanent Python stored
procedure in Snowflake, via Snowpark's session.sproc.register_from_file.

Each node's pyproject.toml `[project.dependencies]` is both what gets
requested from Snowflake's Anaconda channel and what `uv sync` installs
locally, so there's one dependency list instead of two that can drift.
Anything not on the Anaconda channel is vendored instead: its wheel (and any
non-Anaconda wheels in its own dependency chain) committed under
procedures/<name>/vendor/, listed in that node's pyproject.toml `vendored`
group for local `uv sync`, and picked up automatically here.

Required env vars (unless --dry-run): SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
SNOWFLAKE_TOKEN, SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE.
"""
import argparse
import os
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROCEDURES_DIR = REPO_ROOT / "procedures"
CONFIG_FILE = REPO_ROOT / "task-graph.yaml"

# PyPI name -> Anaconda channel name, where they differ (e.g. torch/pytorch).
ANACONDA_PACKAGE_NAME_OVERRIDES = {
    "torch": "pytorch",
}


def load_config():
    return yaml.safe_load(CONFIG_FILE.read_text())


def anaconda_packages(node_dir):
    """Packages to request from Snowflake's Anaconda channel, from
    pyproject.toml's [project.dependencies]. Vendored deps live in that
    file's `vendored` group instead and aren't returned here -- see
    vendor_imports()."""
    data = tomllib.loads((node_dir / "pyproject.toml").read_text())
    packages = []
    for dep in data["project"]["dependencies"]:
        name, _, version = dep.partition("==")
        anaconda_name = ANACONDA_PACKAGE_NAME_OVERRIDES.get(name, name)
        packages.append(f"{anaconda_name}=={version}" if version else anaconda_name)
    return packages


def load_procedures():
    procedures = {}
    for manifest in sorted(PROCEDURES_DIR.glob("*/procedure.yaml")):
        data = yaml.safe_load(manifest.read_text())
        node_dir = manifest.parent
        entrypoint = (node_dir / data["entrypoint"]).resolve()
        procedures[data["name"]] = {
            "depends_on": data.get("depends_on", []),
            "entrypoint": entrypoint,
            "handler": data["handler"],
            "packages": anaconda_packages(node_dir),
            "vendor_dir": node_dir / "vendor",
            "external_access_integrations": data.get("external_access_integrations", []),
        }

    for name, p in procedures.items():
        unknown = [d for d in p["depends_on"] if d not in procedures]
        if unknown:
            raise ValueError(f"{name} depends_on unknown service(s): {unknown}")

    return procedures


def sibling_imports(entrypoint):
    """Every other file/folder next to the entrypoint in its src/ dir, so a
    node's app logic can be a package rather than one flat file."""
    src_dir = entrypoint.parent
    return sorted(
        str(item)
        for item in src_dir.iterdir()
        if item.resolve() != entrypoint and item.name != "__pycache__"
    )


def vendor_imports(vendor_dir):
    """Vendored wheels/zips from procedures/<name>/vendor/, if present."""
    if not vendor_dir.is_dir():
        return []
    return sorted(str(item) for item in vendor_dir.iterdir())


def proc_name(name):
    # Snowflake unquoted identifiers can't contain hyphens.
    return f"{name.replace('-', '_')}_proc"


def register(dry_run):
    config = load_config()
    procedures = load_procedures()

    if dry_run:
        print("--dry-run: would register the following permanent stored procedures:")
        for name, p in procedures.items():
            rel_entry = p["entrypoint"].relative_to(REPO_ROOT)
            imports = [
                str(Path(i).relative_to(REPO_ROOT)) for i in sibling_imports(p["entrypoint"])
            ]
            vendored = [
                str(Path(i).relative_to(REPO_ROOT)) for i in vendor_imports(p["vendor_dir"])
            ]
            print(f"-- {proc_name(name)} --")
            print(f"  entrypoint: {rel_entry}:{p['handler']}")
            print(f"  imports:    {imports or '(none)'}")
            print(f"  vendored:   {vendored or '(none)'}")
            print(f"  packages:   {p['packages']}")
            print(f"  ext access: {p['external_access_integrations'] or '(none)'}")
        return

    from snowflake.snowpark import Session

    session = Session.builder.configs(
        {
            "account": os.environ["SNOWFLAKE_ACCOUNT"],
            "user": os.environ["SNOWFLAKE_USER"],
            "authenticator": "oauth",
            "token": os.environ["SNOWFLAKE_TOKEN"],
            "role": os.environ["SNOWFLAKE_ROLE"],
            "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
            "database": config["database"],
            "schema": config["schema"],
        }
    ).create()

    try:
        session.sql(f"CREATE STAGE IF NOT EXISTS {config['stage']}").collect()

        for name, p in procedures.items():
            target = proc_name(name)
            imports = sibling_imports(p["entrypoint"]) + vendor_imports(p["vendor_dir"])
            print(f"Registering {target} from {p['entrypoint'].relative_to(REPO_ROOT)}:{p['handler']}")
            session.sproc.register_from_file(
                file_path=str(p["entrypoint"]),
                func_name=p["handler"],
                name=target,
                is_permanent=True,
                stage_location=f"@{config['stage']}",
                imports=imports or None,
                packages=p["packages"],
                external_access_integrations=p["external_access_integrations"] or None,
                replace=True,
            )
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    register(args.dry_run)
