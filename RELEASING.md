# Releasing `anakin-sdk` to PyPI

The repo ships with a GitHub Actions workflow at
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) that
builds and publishes on every `v*` tag. You don't run `twine upload`
manually — push a tag and the workflow does it.

## One-time setup

1. **Configure trusted publishing** on PyPI (recommended over an API token):
   - https://pypi.org/manage/account/publishing/
   - Project name: `anakin-sdk`
   - Owner: `Anakin-Inc`
   - Repository: `anakin-py`
   - Workflow: `publish.yml`
   - Environment: `pypi`
2. **Create the GitHub environments** with the same names (`pypi`, `testpypi`)
   under `Settings → Environments`. Add reviewers if you want a manual
   approval gate before publish.
3. **Optional**: configure trusted publishing on TestPyPI the same way
   (use the `testpypi` environment) for dry-run publishes.

No secrets to store anywhere — trusted publishing uses GitHub OIDC.

## Cutting a release

1. Bump the version:
   ```bash
   # src/anakin/_version.py
   __version__ = "0.2.1"
   ```
   (the workflow asserts the tag and the file match)

2. Move the `[Unreleased]` notes in `CHANGELOG.md` under the new version and
   date. Call out anything breaking.

3. Make sure the generated async client is current and run the live smoke test:
   ```bash
   python scripts/generate_async.py --check
   ANAKIN_API_KEY=ak-... python examples/smoke_test.py
   ```

4. Commit, tag, push:
   ```bash
   git add src/anakin/_version.py CHANGELOG.md
   git commit -m "release: v0.2.1"
   git tag v0.2.1
   git push origin main --tags
   ```

5. The `publish.yml` workflow fires on the tag, builds wheel + sdist,
   verifies the version, and publishes to PyPI.

6. Verify: `pip install anakin-sdk==0.2.1 --no-cache-dir`

## Dry run via TestPyPI

Use the `workflow_dispatch` trigger:

- GitHub UI → Actions → "Publish to PyPI" → "Run workflow" → select `testpypi`
- Or: `gh workflow run publish.yml -f target=testpypi`

Then install the test build:
```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ anakin-sdk
```
