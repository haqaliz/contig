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
   - builds standalone binaries for Linux, macOS (arm64 and x64), and Windows,
   - creates the GitHub Release and attaches all of them,
   - publishes the CLI image to GHCR (`ghcr.io/haqaliz/contig:<tag>` and `:latest`),
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

### PyPI (trusted publishing, no token)

One time, on PyPI:

1. If the name `contig` is taken, rename the project in `pyproject.toml` first (for
   example `contig-bio`) and update the install docs.
2. On PyPI, add a Trusted Publisher for the project: owner `haqaliz`, repository
   `contig`, workflow `release.yml`, environment `pypi`. (Create the project by
   uploading once manually if PyPI requires it, or use the "pending publisher" flow.)

The `pypi` job uses OIDC (`id-token: write`), so no API token secret is stored.

### Homebrew tap

1. Create a public repo `haqaliz/homebrew-contig`.
2. After a release builds the binaries, compute their checksums and fill them into
   `homebrew/contig.rb`:

   ```bash
   for a in contig-macos-arm64 contig-macos-x86_64 contig-linux-x86_64; do
     curl -fsSL -o "$a" "https://github.com/haqaliz/contig/releases/download/v0.1.0/$a"
     shasum -a 256 "$a"
   done
   ```

3. Commit the filled formula to the tap as `Formula/contig.rb`. Users then run
   `brew install haqaliz/contig/contig`.

This step is manual per release for now (the checksums change each build). A future
job can update the tap automatically with a tap-scoped token.

## Note on the runtime

However it is installed, the `contig` binary is the CLI. The self-contained commands
(plan, show, verify, benchmark, eval-detector, clusters, coverage, methods, export,
cost, keygen) work standalone. A real pipeline run (`contig run`) also needs Nextflow,
a Java runtime, and a container runtime on the machine; that is external to packaging.
