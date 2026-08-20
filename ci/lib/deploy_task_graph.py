"""
Reconciles a Snowflake Task Graph from the procedures/*/procedure.yaml
manifests in this repo and task-graph.yaml (database/schema/stage/DAG
name). Adding a node to the graph is just adding a new procedures/<name>/
directory -- this script discovers nodes by scanning, no per-service code
here. Mirrors ci/lib/deploy_task_graph.py from the SPCS task-graph pipeline
this repo is modeled on, minus the compute-pool/image plumbing that has no
equivalent for stored procedures.

Uses the Snowflake Python API (snowflake.core.task.dagv1: DAG, DAGTask,
DAGOperation) to build and deploy the graph -- no hand-written CREATE/ALTER/
SUSPEND/RESUME TASK SQL. DAGOperation owns creating, altering and the
leaf-to-root resume ordering Snowflake requires.

Each task's body is a plain `CALL <name>_proc()` statement invoking the
permanent stored procedure that ci/lib/register_procedures.py already
uploaded and created (the "build" step in this pipeline). That CALL string
is the one thing here with no snowflake.core equivalent -- DAGTask accepts a
Callable/StoredProcedureCall too, but those register an *anonymous* sproc
from a live Python object, which would mean re-uploading + re-executing each
node's handler code in this process instead of just referencing the
permanent procedure that build step already registered.

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
        procedures[data["name"]] = data.get("depends_on", [])

    for name, deps in procedures.items():
        unknown = [d for d in deps if d not in procedures]
        if unknown:
            raise ValueError(f"{name} depends_on unknown service(s): {unknown}")

    return procedures


def topological_order(procedures):
    """Pure-Python pre-flight check (Kahn's algorithm): fails fast with a
    clear cycle error before the graph ever reaches Snowflake, and drives the
    --dry-run summary. Roots-first order."""
    remaining = {name: set(deps) for name, deps in procedures.items()}
    order = []

    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError(
                f"cycle detected in task graph, involving: {sorted(remaining)}"
            )
        for name in ready:
            order.append(name)
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)

    return order


def proc_name(name):
    # Must match register_procedures.py's proc_name -- Snowflake unquoted
    # identifiers can't contain hyphens, and this is embedded in a raw
    # `CALL` statement rather than going through the structured DAG/Task API.
    return f"{name.replace('-', '_')}_proc"


def call_statement(name):
    return f"CALL {proc_name(name)}()"


def build_dag(config, procedures, warehouse):
    from snowflake.core.task.dagv1 import DAG, DAGTask

    dag = DAG(config["dag_name"])
    with dag:
        tasks = {
            name: DAGTask(name, call_statement(name), warehouse=warehouse)
            for name in procedures
        }
        for name, deps in procedures.items():
            for dep in deps:
                tasks[dep] >> tasks[name]  # dep runs before name
    return dag


def run(dry_run):
    config = load_config()
    procedures = load_procedures()
    order = topological_order(procedures)

    print("Task graph resolution order (roots first):")
    for name in order:
        deps = procedures[name]
        print(f"  {name}" + (f"  (after: {', '.join(deps)})" if deps else ""))

    if dry_run:
        print(
            f"\n--dry-run: would deploy DAG '{config['dag_name']}' to "
            f"{config['database']}.{config['schema']} via "
            f"DAGOperation.deploy(mode=CreateMode.or_replace), then "
            f"DAGOperation.run() to trigger it once. Each task's body:\n"
        )
        for name in order:
            print(f"  {name}: {call_statement(name)}")
        return

    import snowflake.connector
    from snowflake.core import CreateMode, Root
    from snowflake.core.task.dagv1 import DAGOperation

    warehouse = os.environ["SNOWFLAKE_WAREHOUSE"]

    connection = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        authenticator="oauth",
        token=os.environ["SNOWFLAKE_TOKEN"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=warehouse,
        database=config["database"],
        schema=config["schema"],
    )
    root = Root(connection)

    schema = root.databases[config["database"]].schemas[config["schema"]]

    dag = build_dag(config, procedures, warehouse)
    dag_op = DAGOperation(schema)
    # or_replace makes redeploys idempotent; DAGOperation owns suspend/resume
    # ordering across the whole graph.
    dag_op.deploy(dag, mode=CreateMode.or_replace)
    dag_op.run(dag)

    connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
