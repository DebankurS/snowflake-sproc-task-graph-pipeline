"""
Registers each procedures/<name>/ node as a permanent Python stored
procedure in Snowflake -- the "build" step, analogous to Kaniko building and
pushing an image per services/<name>/Dockerfile in the SPCS task-graph
pipeline this repo is modeled on.

Each node's application logic lives in its own procedures/<name>/src/ folder
-- an arbitrarily deep package, not a single file, and never inlined as a
string in this script or in deploy_task_graph.py. Adding a task graph node
is just adding a new procedures/<name>/ directory with a procedure.yaml +
src/ -- this script discovers nodes by scanning, no per-service code here.

Uses Snowpark's StoredProcedureRegistration.register_from_file
(session.sproc.register_from_file) to upload each node's entrypoint file
plus every other file/folder alongside it in src/ (auto-zipped, structure
preserved) to the permanent stage from task-graph.yaml, and
CREATE OR REPLACE PROCEDURE the result -- no hand-written CREATE PROCEDURE
SQL. register_from_file uploads the entrypoint file's bytes directly rather
than importing it as a Python module in this process, so this script never
needs whatever third-party packages a node's own handler code imports --
only PyYAML and snowflake-snowpark-python, same as deploy_task_graph.py.

Required env vars (unless --dry-run): SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER,
SNOWFLAKE_TOKEN, SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE.
"""
import argparse
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROCEDURES_DIR = REPO_ROOT / "procedures"
CONFIG_FILE = REPO_ROOT / "task-graph.yaml"


def load_config():
    return yaml.safe_load(CONFIG_FILE.read_text())


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
            "packages": data.get("packages", ["snowflake-snowpark-python"]),
        }

    for name, p in procedures.items():
        unknown = [d for d in p["depends_on"] if d not in procedures]
        if unknown:
            raise ValueError(f"{name} depends_on unknown service(s): {unknown}")

    return procedures


def sibling_imports(entrypoint):
    """Every other file/folder next to the entrypoint inside its src/ dir --
    passed as `imports` so register_from_file bundles them (auto-zipped,
    structure preserved) without re-uploading the entrypoint file itself
    twice. This is what lets a node's app logic be a whole package (e.g.
    src/handler.py importing src/lib/*.py) instead of one flat file, with no
    per-node special-casing here."""
    src_dir = entrypoint.parent
    return sorted(
        str(item) for item in src_dir.iterdir() if item.resolve() != entrypoint
    )


def proc_name(name):
    # Snowflake unquoted identifiers can't contain hyphens; this name gets
    # embedded in a raw `CALL` statement (deploy_task_graph.py), unlike node
    # names themselves which go through the structured DAG/Task API and get
    # quoted automatically.
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
            print(f"-- {proc_name(name)} --")
            print(f"  entrypoint: {rel_entry}:{p['handler']}")
            print(f"  imports:    {imports or '(none)'}")
            print(f"  packages:   {p['packages']}")
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

    session.sql(f"CREATE STAGE IF NOT EXISTS {config['stage']}").collect()

    for name, p in procedures.items():
        target = proc_name(name)
        print(f"Registering {target} from {p['entrypoint'].relative_to(REPO_ROOT)}:{p['handler']}")
        session.sproc.register_from_file(
            file_path=str(p["entrypoint"]),
            func_name=p["handler"],
            name=target,
            is_permanent=True,
            stage_location=f"@{config['stage']}",
            imports=sibling_imports(p["entrypoint"]) or None,
            packages=p["packages"],
            replace=True,
        )

    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    register(args.dry_run)
