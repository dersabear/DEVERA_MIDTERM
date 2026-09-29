# Forwarded Static Assets Plan

- **Status:** Forwarded static asset fix is committed, merged to `main`, verified, and documented.
- **Created:** 2026-09-29 07:25:03 UTC
- **Study:** `doc/study/1790666629_static-assets-forwarded-prefix.md`
- **Scope:** Make LightChat CSS and JavaScript URLs work under the CodeRange forwarded path and at the normal local root.

## Objective

Fix static asset requests that currently go to `/static/lightchat/...` instead of the mounted CodeRange path. Do not hard-code a hostname, session identifier, proxy port, or an undocumented forwarding header.

## Decisions

- Use Django's per-request WSGI `SCRIPT_NAME` as the mounted path prefix.
- Keep `STATIC_URL` at `/static/` for stable local asset routing.
- Add a small request-aware template tag for LightChat's static links. It will prefix local static URLs with `SCRIPT_NAME` when present, and leave root-local URLs unchanged when it is empty.
- Use a prefix-aware `runserver` static handler that serves from `request.path_info`, not `request.path`, because `request.path` includes `SCRIPT_NAME` and makes the default development handler look up a path that includes the mount prefix.
- Keep Django's `django.contrib.staticfiles` finders and development serving. Do not add a React/Vite build or a new asset server.
- Do not change host, CSRF, or forwarded-header settings as part of this static asset fix.

## Implementation Task Board

### Phase 0: Prepare

- [x] Confirm `main` is clean and create `fix/forwarded-static-assets` from `main`.
- [x] Confirm that no canonical documentation conflicts with the planned local static URL behavior.

### Phase 1: Make static URL generation mount-aware

- [x] Add a LightChat template tag that uses the current request's `SCRIPT_NAME` to prefix static URLs.
- [x] Use the tag for `app.css` and `app.js` in the shared base template.
- [x] Set `STATIC_URL` to a stable root `/static/`; do not put the forwarded prefix or port in settings.
- [x] Override the `runserver` static handler in the LightChat app so mounted static requests use `request.path_info` for file lookup.
- [x] Preserve normal local output when `SCRIPT_NAME` is empty.
- [x] Keep the fix limited to static asset URLs. Leave Django URL routing, login routes, and provider settings unchanged.

### Phase 2: Verify forwarded and local asset requests

- [x] Test login-page rendering with a dynamically supplied `SCRIPT_NAME` such as `/proxy/<port>` and confirm both asset URLs include that prefix.
- [x] Use Django's prefix-aware staticfiles handler with `SCRIPT_NAME` set and request both `app.css` and `app.js`; confirm HTTP 200 and correct content types.
- [x] Test the same assets with an empty `SCRIPT_NAME`; confirm normal local URLs still return HTTP 200.
- [x] Confirm login, sign-up, and form URLs keep the mount prefix and remain usable.
- [x] Run `.venv/bin/python manage.py check`, migration checks, `.venv/bin/python manage.py test`, `node --check lightchat/static/lightchat/app.js`, and `manage.py runserver --help`.
- [x] Use Django's standard WSGI `SCRIPT_NAME` in the forwarded-prefix tests. No CodeRange hostname or port is hard-coded.

**Verification result:** Login renders the prefixed CSS/JS URLs. The prefix-aware Django static handler returns HTTP 200 for both assets with a generated mount prefix and at the local root. A login POST and the post-login page also work with the mount prefix. The custom `runserver` command uses the prefix-aware static wrapper because Django's default handler includes `SCRIPT_NAME` in `request.path` during file lookup. All 32 Django tests pass. Visual inspection in a CodeRange browser was not available in this shell.

### Phase 3: Commit and rendezvous

- [x] Review the diff. Suggested commit: `fix: serve static assets under CodeRange prefix`.
- [x] Commit the change as `7fcf13f fix: serve static assets under CodeRange prefix`.
- [x] Fast-forward merge the implementation branch into `main` and rerun checks after the merge.
- [x] Update the task board with the merge and verification result.

### Phase 4: Sync living docs

- [x] Update the local development page in `doc/wiki/` with the mount-aware static behavior.
- [x] Add a `doc/wiki/footguns/forwarded-static-assets.md` note for the WSGI `SCRIPT_NAME` and static-handler behavior.
- [x] Keep the documentation scoped to behavior verified by the code and tests. Do not change `doc/canonical/`.

## Acceptance Criteria

- A login page rendered with a forwarded `SCRIPT_NAME` links to `/proxy/<current-prefix>/static/lightchat/app.css` and `/proxy/<current-prefix>/static/lightchat/app.js` without a hard-coded host or port.
- Both static assets return HTTP 200 through Django's staticfiles handler under the forwarded prefix.
- Both assets also return HTTP 200 at the normal local root.
- The login page loads its styles and JavaScript and retains its login and sign-up interactions.
- No credentials, session hostname, or proxy port are added to tracked files.
- Checks and tests pass before and after the merge to `main`.
