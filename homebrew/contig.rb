# Homebrew formula for the contig CLI. This installs the standalone release binary
# (no Python needed). It lives here as the source of truth; the published tap is a
# separate repo, haqaliz/homebrew-contig, where this file goes as Formula/contig.rb.
# After a release builds the binaries, fill in the sha256 values (see RELEASING.md),
# commit to the tap, then: brew install haqaliz/contig/contig.
#
# A real pipeline run still needs Nextflow, a Java runtime, and a container runtime;
# the self-contained commands work without them.
class Contig < Formula
  desc "Agentic bioinformatics analyst: the Layer-2 run, self-heal, verify, reproduce engine"
  homepage "https://github.com/haqaliz/contig"
  version "0.58.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.58.0/contig-macos-arm64"
      sha256 "c976402187955a391b016ad1661f603cd06f9356c153f88265dbeb37833c0bb8"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.58.0/contig-macos-x86_64"
      sha256 "62ef818ecef99ce1360011bfaeff1fb07d1770ad6b8d03400390b060ea7dfec8"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.58.0/contig-linux-x86_64"
    sha256 "a67e711d1568e4000e1789c86da58b282c2ef84f03cfcc6bfa4d2e70c6acbb1f"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.58.0", shell_output("#{bin}/contig version")
  end
end