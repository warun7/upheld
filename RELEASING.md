# Releasing

upheld is published to PyPI by [`.github/workflows/publish.yml`](.github/workflows/publish.yml) when a version tag is pushed. PyPI trusts that workflow through [trusted publishing](https://docs.pypi.org/trusted-publishers/), so there is no API token to create or store.

## One-time setup

1. Create a PyPI account at <https://pypi.org/account/register/> and turn on two-factor authentication, which PyPI requires before you can publish.
2. Go to <https://pypi.org/manage/account/publishing/> and add a pending publisher for GitHub:
   - PyPI project name: `upheld`
   - Owner: `warun7`
   - Repository name: `upheld`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

   This doesn't reserve the name. The project is created by the first successful publish, and becomes yours then.
3. In the GitHub repository, open Settings → Environments → New environment and name it `pypi`. Adding yourself as a required reviewer makes each release wait for your approval before it reaches PyPI.

## Each release

1. Set the new version with `uv version 0.1.1`, which edits `pyproject.toml` and `uv.lock`.
2. Commit it and push to `main`.
3. Tag the commit and push the tag:

   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```

The workflow checks that the tag matches the version in `pyproject.toml`, runs the tests, builds the sdist and wheel, audits `examples/glp1.json` with the built wheel, and publishes. If the `pypi` environment has a required reviewer, approve the deployment under the run in the Actions tab.

A version can be published only once. If a release goes wrong, fix it and publish the next version.
