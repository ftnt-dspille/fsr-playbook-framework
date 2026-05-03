# FSRPlaybookYaml (`fsrpb`)

YAML → FortiSOAR playbook JSON compiler, plus a SQLite reference store of
every connector, operation, parameter, step type, module field, Jinja
macro, and recipe available locally.

Live plan: [`Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md`](../Miscellaneous/FSR_PLAYBOOK_YAML_PLAN.md)

## Layout

```
python/      probes (build SQLite), Python compiler, e2e harness, CLI
ts/          TypeScript compiler (widget-runnable, consumes fsr_reference.json)
store/       schema.sql + generated fsr_reference.{db,json} + agent .md exports
examples/    YAML fixtures + expected JSON
tests/       pytest + vitest
```

## SQLite-first

Everything an agent needs is queryable via SQL. `store/fsr_reference.db` is
the single source of truth; `store/fsr_reference.json` is a derived export
for the TS compiler / widget.

The DB ATTACHes `Miscellaneous/api_examples_catalog/catalog.sqlite`
read-only as `catalog` so probes can join against the existing
`connector_lifecycle` and cross-vendor `entries` tables.

## Dev setup

```sh
# python
python -m venv .venv && source .venv/bin/activate
pip install -e ../pyfsr -e .
fsrpb refresh                  # run all probes, rebuild store + json

# ts
cd ts && pnpm install && pnpm build
```

## pyfsr enhancements

This project drives new dedicated actions into `pyfsr` rather than
hand-rolling HTTP calls (workflow-collection import, playbook trigger/poll,
bulk record create, etc.). New methods land in pyfsr with tests, then
get used here.
