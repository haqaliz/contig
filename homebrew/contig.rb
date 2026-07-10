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
  version "0.25.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.25.0/contig-macos-arm64"
      sha256 "7efc4e478f210fefa98cedb9213747e1e095574003908f12484189a9ff87c60b"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.25.0/contig-macos-x86_64"
      sha256 "18da5f9bdeec8a8d96156a7836b7fca5fd42372fb0674d420e5d380f3966fa06"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.25.0/contig-linux-x86_64"
    sha256 "1bf681a1dd7a418e33b53bd7b954b4ba4e8513760a5495133cb4e3ead328a64d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.25.0", shell_output("#{bin}/contig version")
  end
end
