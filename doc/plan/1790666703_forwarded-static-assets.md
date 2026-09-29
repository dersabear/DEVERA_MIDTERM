# Forwarded Static Assets Plan

- **Status:** Ready for execution. No application code has been changed in this stage.
- **Created:** 2026-09-29 07:25:03 UTC
- **Study:** `doc/study/1790666629_static-assets-forwarded-prefix.md`
- **Scope:** Make LightChat CSS and JavaScript URLs work under the CodeRange forwarded path and at the normal local root.

## Objective

Fix static asset requests that currently go to `/static/lightchat/...` instead of the mounted CodeRange path. Do not hard-code a hostname, session identifier, proxy port, or an undocumented forwarding header.

## Decisions

- Use Django's per-request WSGI `SCRIPT_NAME` as the mounted path prefix.
- Keep `STATIC_URL` at `/static/` for stable local asset routing.
- Add a small request-aware template tag for LightChat's static links. It will prefix local static URLs with `SCRIPT_NAME` when present, and leave root-local URLs unchanged when it is empty.
- Keep Django's `django.contrib.staticfiles` development serving. Do not add a React/Vite build or a new asset server.
- Do not change host, CSRF, or forwarded-header settings as part of this static asset fix.

## Implementation Task Board

### Phase 0: Prepare

- [ ] Confirm `main` is clean and create an implementation branch from `main`.
- [ ] Confirm that no canonical documentation conflicts with the planned local static URL behavior.

### Phase 1: Make static URL generation mount-aware

- [ ] Add a LightChat template tag that uses the current request's `SCRIPT_NAME` to prefix static URLs.
- [ ] Use the tag for `app.css` and `app.js` in the shared base template.
- [ ] Set `STATIC_URL` to a stable root `/static/`; do not put the forwarded prefix or port in settings.
- [ ] Preserve normal local output when `SCRIPT_NAME` is empty.
- [ ] Keep the fix limited to static asset URLs. Leave Django URL routing, login routes, and provider settings unchanged.

### Phase 2: Verify forwarded and local asset requests

- [ ] Test login-page rendering with a dynamically supplied `SCRIPT_NAME` such as `/proxy/<port>` and confirm both asset URLs include that prefix.
- [ ] Use Django's staticfiles handler with `SCRIPT_NAME` set and request both `app.css` and `app.js`; confirm HTTP 200 and correct content types.
- [ ] Test the same assets with an empty `SCRIPT_NAME`; confirm normal local URLs still return HTTP 200.
- [ ] Confirm login, sign-up, and form URLs keep the mount prefix and remain usable.
- [ ] Run `.venv/bin/python manage.py check`, migration checks, `.venv/bin/python manage.py test`, and `node --check lightchat/static/lightchat/app.js`.
- [ ] If CodeRange does not provide a usable `SCRIPT_NAME`, do not guess a proxy header. Stop and report the missing mount-prefix behavior.

### Phase 3: Commit and rendezvous

- [ ] Review the diff and commit as `fix: serve static assets under CodeRange prefix`.
- [ ] Fast-forward merge the implementation branch into `main` and rerun checks after the merge.
- [ ] Update the task board with the merge and verification result.

### Phase 4: Sync living docs

- [ ] Update the local development page in `doc/wiki/` with the mount-aware static behavior.
- [ ] Add a `doc/wiki/footguns/` note if static URLs depend on WSGI `SCRIPT_NAME` under a forwarded path.
- [ ] Keep the documentation scoped to behavior verified by the code and tests. Do not change `doc/canonical/`.

## Acceptance Criteria

- A login page rendered with a forwarded `SCRIPT_NAME` links to `/proxy/<current-prefix>/static/lightchat/app.css` and `/proxy/<current-prefix>/static/lightchat/app.js` without a hard-coded host or port.
- Both static assets return HTTP 200 through Django's staticfiles handler under the forwarded prefix.
- Both assets also return HTTP 200 at the normal local root.
- The login page loads its styles and JavaScript and retains its login and sign-up interactions.
- No credentials, session hostname, or proxy port are added to tracked files.
- Checks and tests pass before and after the merge to `main`.
