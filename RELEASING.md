# Releasing `anakin` to PyPI

The repo ships with a GitHub Actions workflow at
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) that
builds and publishes on every `v*` tag. You don't run `twine upload`
manually — push a tag and the workflow does it.

## One-time setup

1. **Configure trusted publishing** on PyPI (recommended over an API token):
   - https://pypi.org/manage/account/publishing/
   - Project name: `anakin`
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

1. Bump the version in two places:
   ```bash
   # src/anakin/_version.py
   __version__ = "0.1.1"
   ```
   (the workflow asserts the tag and the file match)

2. Update the CHANGELOG (none yet — start one when there's a user-facing
   change to log).

3. Commit, tag, push:
   ```bash
   git add src/anakin/_version.py
   git commit -m "release: v0.1.1"
   git tag v0.1.1
   git push origin main --tags
   ```

4. The `publish.yml` workflow fires on the tag, builds wheel + sdist,
   verifies the version, and publishes to PyPI.

5. Verify: `pip install anakin-sdk==0.1.1 --no-cache-dir`

## Dry run via TestPyPI

Use the `workflow_dispatch` trigger:

- GitHub UI → Actions → "Publish to PyPI" → "Run workflow" → select `testpypi`
- Or: `gh workflow run publish.yml -f target=testpypi`

Then install the test build:
```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ anakin
```
