# Releasing Contig

Releases are cut by pushing a version tag. The release runs in the
**haqaliz/contig** repo with the repo's `GITHUB_TOKEN`, so the GitHub Release and the
GHCR image are owned by the repository, not by whatever account the local `gh` CLI is
logged into. Do not run `gh release create` by hand; let the workflow do it.

## Cut a release

1. Bump the version in `pyproject.toml` and add a section to `CHANGELOG.md`.
2. Commit and push to `master`. Make sure CI is green.
3. Tag and push the tag (this is a plain git push, it uses the repo's git identity):

   ```bash
   git tag -a v0.1.0 -m "contig 0.1.0"
   git push origin v0.1.0
   ```

4. The `release` workflow (`.github/workflows/release.yml`) then, in parallel:
   - builds the wheel and sdist,
   - builds standalone binaries for Linux, macOS arm64, and Windows in the `binaries`
     matrix, and the macOS x64 binary in a dedicated `binary-macos-intel` job that
     builds under Rosetta on the Apple Silicon runner (the macOS Intel runners queue
     indefinitely, so we no longer wait on them),
   - creates the GitHub Release and attaches all of them,
   - publishes the CLI image to GHCR (`ghcr.io/haqaliz/contig:<tag>` and `:latest`)
     plus Docker Hub when the `DOCKERHUB_USERNAME` secret is set,
   - publishes to PyPI (if trusted publishing is set up, see below).

Watch it with `gh run watch` or the Actions tab. Each channel is an independent job,
so one failing does not block the others.

## One-time setup per channel

### Binaries and the GitHub Release

Nothing to set up. They use the repo `GITHUB_TOKEN`.

### GHCR (container image)

Nothing to set up for publishing (the workflow uses `GITHUB_TOKEN` with
`packages: write`). After the first push, make the package public in the repo's
Packages settings if you want anonymous `docker pull`.

### Docker Hub (optional second registry)

The `docker` job also pushes to Docker Hub, but only when the
`DOCKERHUB_USERNAME` repository secret is set. If it is unset the Docker Hub
steps are skipped and only GHCR is published. One time, to enable it:

1. On Docker Hub, create a public repository named `contig` under the account
   that owns the image (it lives at `docker.io/<username>/contig`).
2. Create a personal access token with Read and Write permission
   (Account Settings, Personal access tokens).
3. Add two repository secrets on GitHub
   (`Settings, Secrets and variables, Actions`):
   - `DOCKERHUB_USERNAME`: the Docker Hub username (also the image namespace).
   - `DOCKERHUB_TOKEN`: the access token from step 2.

The image is then published as `docker.io/<username>/contig:<tag>` and `:latest`
alongside the GHCR tags.

### PyPI (trusted publishing, no token)

One time, on PyPI:

1. If the name `contig` is taken, rename the project in `pyproject.toml` first (for
   example `contig-bio`) and update the install docs.
2. On PyPI, add a Trusted Publisher for the project: owner `haqaliz`, repository
   `contig`, workflow `release.yml`, environment `pypi`. (Create the project by
   uploading once manually if PyPI requires it, or use the "pending publisher" flow.)

The `pypi` job uses OIDC (`id-token: write`), so no API token secret is stored.

### Homebrew tap

The tap repo `haqaliz/homebrew-contig` already exists (public). The formula lives
there as `Formula/contig.rb`; `homebrew/contig.rb` in this repo is the source of
truth that gets copied over. Per release:

1. After a release builds the binaries, compute their checksums and fill them into
   `homebrew/contig.rb` (also bump the `version` and the three release URLs):

   ```bash
   for a in contig-macos-arm64 contig-macos-x86_64 contig-linux-x86_64; do
     curl -fsSL -o "$a" "https://github.com/haqaliz/contig/releases/download/vX.Y.Z/$a"
     shasum -a 256 "$a"
   done
   ```

2. Copy the filled formula to the tap as `Formula/contig.rb` and push (the tap
   pushes over SSH as the `haqaliz` identity). Users then run
   `brew install haqaliz/contig/contig`.

This step is manual per release for now (the checksums change each build). A future
job can update the tap automatically with a tap-scoped token.

CI now builds `contig-macos-x86_64` in the `binary-macos-intel` job (Rosetta on the
Apple Silicon runner), so it should be on the release automatically. Only if that
job ever fails and `contig-macos-x86_64` is missing, build it locally on an Apple
Silicon machine under Rosetta (the same steps the job runs) and upload it as
`haqaliz` (not the push-only collaborator):

```bash
# x86_64 Python 3.12 (uv is arm64-only, so fetch a standalone build)
curl -fsSL -o py.tgz "https://github.com/astral-sh/python-build-standalone/releases/latest/download/cpython-3.12-x86_64-apple-darwin-install_only.tar.gz" || \
  echo "pick the exact asset URL from the python-build-standalone latest release"
tar -xzf py.tgz -C /tmp/py-x64
arch -x86_64 /tmp/py-x64/python/bin/python3 -m venv /tmp/contig-x64
arch -x86_64 /tmp/contig-x64/bin/python -m pip install --only-binary=:all: cryptography pydantic typer
arch -x86_64 /tmp/contig-x64/bin/python -m pip install --no-deps . pyinstaller
arch -x86_64 /tmp/contig-x64/bin/pyinstaller --onefile --name contig \
  --collect-submodules contig --copy-metadata contig \
  --add-data "src/contig/data:contig/data" packaging/contig_main.py
mv dist/contig dist/contig-macos-x86_64
gh release upload vX.Y.Z dist/contig-macos-x86_64 --repo haqaliz/contig
```

## Note on the runtime

However it is installed, the `contig` binary is the CLI. The self-contained commands
(plan, show, verify, benchmark, eval-detector, clusters, coverage, methods, export,
cost, keygen) work standalone. A real pipeline run (`contig run`) also needs Nextflow,
a Java runtime, and a container runtime on the machine; that is external to packaging.
