# snowflake-sproc-task-graph-pipeline

A reference pipeline for deploying a **Snowflake Task Graph** (a DAG of
Snowflake Tasks) where each task runs as a **permanent Python stored
procedure**, driven end-to-end by GitLab CI. Modeled on the sibling
[`snowflake-spcs-task-graph-pipeline`](../snowflake-spcs-task-graph-pipeline)
repo, which does the same thing for SPCS container jobs instead.

Each node in the graph is a Python package under `procedures/<name>/src/`.
The dependency edges between nodes come from each node's own
`procedure.yaml` (same idea as that repo's `service.yaml`); Snowflake-side
config (database, schema, stage, DAG name) comes from `task-graph.yaml`.
Adding a task to the graph is just adding a new `procedures/<name>/`
directory -- no CI or deploy-script changes required.

## Why stored procedures need a "build" step at all

A node's application logic is never inlined into a deploy script as a
Python string -- it's a real folder (`procedures/<name>/src/`) that can be
as deep and multi-module as it needs to be (see `procedures/task-b/` for an
example with a `lib/` submodule). Snowflake's `CREATE PROCEDURE` supports
pointing `HANDLER` at a function inside code that's already sitting on a
stage, with no `AS` clause needed -- so, just like the SPCS pipeline builds
an image once and references it by tag, this pipeline uploads each node's
code once (as a permanent stored procedure) and has task bodies reference it
by name.

## How it works

The GitLab pipeline (`.gitlab-ci.yml`) has two stages:

1. **`register`** -- `ci/lib/register_procedures.py` scans
   `procedures/*/procedure.yaml`, and for each node uploads its entrypoint
   file plus everything else alongside it in `src/` (via Snowpark's
   `session.sproc.register_from_file`, using `imports` for the rest of the
   package -- auto-zipped, structure preserved) and `CREATE OR REPLACE`s a
   permanent stored procedure named `<name>_proc`. This never imports a
   node's own code into the CI process, so this script's dependencies stay
   fixed (`snowflake-snowpark-python`, `pyyaml`) regardless of what any
   node's handler code itself imports.
2. **`deploy`** -- `ci/lib/deploy_task_graph.py` scans the same manifests to
   discover nodes and edges, then builds and deploys a
   `snowflake.core.task.dagv1.DAG` via the Snowflake Python API. Each task's
   body is a single `CALL <name>_proc()` statement invoking the procedure
   the register stage already created -- the one statement in this whole
   pipeline that references an object by name rather than going through
   `snowflake.core`.

Both stages only run on pushes to `main`.

## Repo layout

```
.gitlab-ci.yml            Pipeline definition (stages, required CI variables)
task-graph.yaml            Snowflake-side config: database, schema, stage, DAG name
procedures/<name>/
  procedure.yaml            name, depends_on (edges in the DAG), entrypoint, handler, packages
  src/                       The node's application code -- its own folder structure,
                             can be arbitrarily complex, never nested inline elsewhere
ci/
  pyproject.toml, uv.lock   Python deps for the register/deploy steps (managed with uv)
  lib/
    get_snowflake_token.sh   Azure AD client-credentials -> Snowflake OAuth token
    register_procedures.py   Discovers nodes, uploads code, creates permanent procedures
    deploy_task_graph.py     Discovers the graph, builds + deploys the DAG
```

## Adding a task

1. Create `procedures/<name>/src/` with the task's application code --
   whatever folder structure it needs. The entrypoint file must define a
   function whose first parameter is the Snowpark `Session` (even if
   unused), per Snowflake's Python stored procedure calling convention.
2. Create `procedures/<name>/procedure.yaml`:
   ```yaml
   name: <name>
   depends_on: [<upstream-task-name>, ...]
   entrypoint: src/handler.py
   handler: run
   packages: [snowflake-snowpark-python]
   ```
3. Push to `main`. The new node is picked up automatically on the next
   register and deploy.

## Prerequisites (one-time, not managed by this pipeline)

- A Snowflake `SECURITY INTEGRATION` of `TYPE = EXTERNAL_OAUTH` configured
  for Azure AD, with a role mapping for the CI service principal.
- An Azure AD App Registration with a client secret, granted access to the
  scope registered against that Snowflake integration.

## Required GitLab CI/CD variables

Set under **Settings > CI/CD > Variables** (mark `AZURE_CLIENT_SECRET` as
Masked + Protected):

| Variable | Description |
|---|---|
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Azure AD App Registration client ID |
| `AZURE_CLIENT_SECRET` | Azure AD App Registration client secret |
| `SNOWFLAKE_OAUTH_SCOPE` | e.g. `api://<app-id>/.default` |
| `SNOWFLAKE_ACCOUNT` | Account identifier, e.g. `myorg-myaccount` |
| `SNOWFLAKE_USER` | Login name the Azure token maps to |
| `SNOWFLAKE_ROLE` | e.g. `tutorial_role` |
| `SNOWFLAKE_WAREHOUSE` | e.g. `tutorial_warehouse` |

## Local dry run

Both scripts support `--dry-run`, which validates the graph (including
cycle detection) and prints what each stage would do without touching
Snowflake:

```sh
cd ci
uv sync
uv run python lib/register_procedures.py --dry-run
uv run python lib/deploy_task_graph.py --dry-run
```
