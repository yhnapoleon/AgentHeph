# Contract fixtures

Two manifests that stress the `agentstudio/v1alpha1` schema from **opposite ends**, so
we learn whether the contract is overfit to BAU *before* we ever consider freezing `v1`
(ROADMAP M0 #8). These are **paper fixtures** — no app is built from them; they exist
only to be validated by the contract tests in [`tests/test_fixtures.py`](../../tests/test_fixtures.py).

| Fixture | Role | Deliberately exercises |
|---|---|---|
| [`bau/`](./bau/manifest.yaml) | First **real** app (banking ML BAU ops) | Native (non-imported) tools, service-account creds, single-tenant, swagger/UI knowledge sources |
| [`expensly/`](./expensly/manifest.yaml) | A **different** second app (generic SaaS, desensitized) | OpenAPI-imported tools, **delegated-user** creds, **multi-tenant**, org-hierarchy **per-row** scope, a **write** tool, `sync`, reserved budget fields |

If a future schema change can express BAU but breaks Expensly (or vice-versa), that is the
signal the contract is overfit — catch it here, on paper, not after wiring a real app.

The Expensly OpenAPI ([`expensly/openapi.yaml`](./expensly/openapi.yaml)) is a tiny
desensitized spec; the contract test asserts every operation it declares has a matching
`effects` entry in the manifest (no operation silently ungoverned).
