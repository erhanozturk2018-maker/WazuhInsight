# Development Workflow

Scope: how to change this repository safely. Not build/run commands
(README) or test procedures (`testing.md`) — specifically the coordination
and sequencing concerns unique to this codebase's split architecture.

## Before any change: locate which side of the boundary it's on

Ask first: does this change affect the dashboard machine, the manager
machine, or the SSH contract between them? (`../architecture/system-overview.md`)
Dashboard-only changes (routes, templates, `data/*.json` schema, session
logic) can be developed and verified locally. Manager-only changes
(`wazuh-integration/**`) cannot be executed in a sandbox — they assume a
live `/var/ossec/etc/ossec.conf`, root/sudo, and real Postfix/Wazuh
services (`testing.md`). Contract changes (anything altering the SSH
argument shape) require the coordinated edit set below.

## First question for any manager-facing change: which channel?

Before anything else, decide whether the Wazuh API can express what you
need. **If it can, it belongs there** — `services/wazuh_api.py` and the
service module that owns the concern. The SSH channel exists only for
host-OS work the API has no vocabulary for (Postfix, rsyslog files,
packages).

Getting this wrong in the SSH direction means writing and deploying a new
manager-side tool, granting it `sudo`, and widening the forced command's
blast radius — to do something the API already implements.

Read `../architecture/wazuh-api.md` before writing the call. Content-Type,
error shape and retry behaviour are measured facts there, not guessable.

## Adding a manager capability over the API

1. **Service module** — a function returning `(ok, result)`, calling
   `wazuh_api.request`. Put it in the module that owns the concern
   (`ossec_config`, `agents`, `custom_files`), not a new one.
2. **Route** — validates format first, and validates *before* calling;
   a rejection that still sends the request is not a rejection. Maps a
   failure to a 502 with the message intact.
3. **Tests** — stub `wazuh_api.request` via `api_stub`, and assert both
   what was sent and, for rejections, that nothing was sent at all.

For `ossec.conf` specifically, mutations go through
`services/ossec_config.py` so they inherit the backup, the lxml round-trip
and the post-write validation. Do not assemble XML anywhere else.

## Adding an opt-in feature unrelated to the manager

`routes/rag.py` is the template for this, not a one-off. Some capabilities
(the RAG assistant is the first) have nothing to do with Wazuh or the
manager at all — they proxy to some other operator-chosen service. These
still go through the dashboard's own backend, never called from the
browser directly (`services/rag_pipeline.py`'s docstring has the CORS/
`localhost`-resolution reasoning), but they pick up one more requirement
the manager-facing features don't have:

1. **A flag in `config.DEFAULT_FEATURE_FLAGS`**, read through
   `storage.load_feature_flags()`/`save_feature_flags()` — the same
   sub-key pattern as `mail`/`plugins` in `settings.json`
   (`../development/coding-standards.md`). Not an environment variable:
   the point is that the feature stays invisible on a dashboard that has
   never been told the other service exists, even if its `.env` URL
   happens to be set. See `../knowledge/design-decisions.md`.
2. **A toggle on Console → Features** (`routes/settings.py`), not a
   confirmation dialog on activation — flipping the flag has no side
   effect on any external system, so there's nothing to confirm.
3. **The flag checked in two places, not one.** `config.feature_enabled()`
   (a Jinja global, read fresh per render — see its docstring for why a
   route-context variable was rejected) gates the sidebar link.
   *Independently*, the route handlers re-check the same flag and refuse
   with a 404 when it's off. Hiding the link is presentation; a request
   that already knows the URL must still be turned away at the route.
4. **A separate service module** (`services/rag_pipeline.py`) with its own
   pooled session, one function per call, `(ok, result)` like every other
   service module — do not fold this into `wazuh_api.py`, which is
   specifically the Wazuh API transport.

## Coordinated-edit checklist: changing the SSH contract

Still applies to the three argument-carrying SSH features (`restart` takes
none, so it has no argument shape to keep in sync). If you add, rename or
reorder an argument sent over SSH, **all of these must change together** or
the system breaks silently — a mismatched argument count fails on the
manager with no dashboard-visible error until tested:

1. The sender in `dashboard_core/services/ssh_transport.py`
   (`run_mail_command_via_ssh`, `run_rsyslog_command_via_ssh` or
   `run_deps_command_via_ssh`) — what is built and quoted. All four
   senders (including `run_restart_command_via_ssh`) share one drain
   loop, `_run()`, in the same module — a bug there affects every SSH
   feature, not just the one you're touching. See its docstring before
   changing how a sender reads a command's result.
2. The receiving tool's argument parsing (`mail_config_tool.py`,
   `rsyslog-config-tool.py` or `dependency_manager_tool.py`) — what is
   expected, in what order.
3. `config-router-wrapper.sh`'s dispatch — only if the *selector word*
   changes. A new selector also needs its own `sudoers` line
   (`deployment.md`), and is a reviewed widening of the blast radius, not
   a routine step (`../security/ssh-boundary.md`).
4. `is_mutating_action()` in the wrapper — if the new action should or
   should not trigger a restart.

Do not skip the manager-side tool's independent validation even if the
route already validates the same field: these scripts can be invoked
directly on the manager, so they must not trust the dashboard.

## Changing anything that could affect service restarts

Restart logic lives in exactly **two** places now, one per channel, and
they must not be confused:

- **SSH-dispatched mutations** (`mail`, `rsyslog`, `deps`) — restart stays
  centralized in `config-router-wrapper.sh`'s post-dispatch checks
  (including the `rsyslog` selector's own rsyslog-only restart). Do not
  add restart calls inside `mail_config_tool.py` or
  `rsyslog-config-tool.py` — this was tried before and produced a real bug
  (`../knowledge/design-decisions.md`). If a new mutating SSH action needs
  a restart, it needs to be recognized by `is_mutating_action()`, not
  given its own restart call.
- **API-backed writes** (`ossec.conf` blocks, decoder/rule files) —
  restart is triggered from the dashboard side, in
  `services/manager_control.py`, over the SSH `restart` selector. This
  exists because API-backed work does not pass through the wrapper at
  all, so it cannot rely on `is_mutating_action()` — the guarantee had to
  be rebuilt on this side after the same silent-no-restart bug shipped a
  second time (`../knowledge/design-decisions.md`, "Restarting after an
  API-backed write"). A new API-backed write path must call
  `push_tree()`/`save_file()`/`delete_file()` (or otherwise go through
  `manager_control.restart_warning()`), not assume the manager will pick
  the change up on its own — it will not.

## When to confirm scope before proceeding

Confirm with the user before: introducing a database or ORM, adding a
further layer of abstraction over the existing module split (a DI container,
a service registry, a plugin system), adding CI config or a second test
framework alongside `pytest`, adding a frontend build step/framework, or
loosening the SSH forced-command's scope in any way. These are all deliberate non-goals or hard boundaries
(`../architecture/system-overview.md`, `../security/ssh-boundary.md`) — a
request that seems to require one of them may actually be solvable within
the existing pattern; check before assuming the boundary itself needs to
move.

## Minimizing footprint

Prefer editing the smallest number of files that correctly implements a
change. For a typical API-backed feature this is the three files the
"Adding a manager capability over the API" steps above name — a service
function, a route, a test — plus a template edit if it needs a new UI
element. Touching the wrapper, a `sudoers` line, or a manager-side tool
should be rare and deliberate: it only happens for the three remaining
SSH features, and adding a new SSH target at all is the reviewed
widening described above, not a routine step. If a change is touching
significantly more files than its category above implies, re-check
against `../architecture/repository-map.md`'s "Finding things by task"
table before proceeding, since it likely means the wrong layer was
chosen.
