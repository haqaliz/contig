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
  version "0.27.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.27.0/contig-macos-arm64"
      sha256 "362c45d17f6fcfd3524d0f817b80edc0bad1ab6f21441223cd07be9394483951"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.27.0/contig-macos-x86_64"
      sha256 "b425d9517c9fe6db9bce162e32966ad543c04e9127d880f4d697c4d2af471bbd"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.27.0/contig-linux-x86_64"
    sha256 "fc96f0f5b18e74cce7cf14797190a3b956cba0d4f6f96735c9daad8531db4f24"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.27.0", shell_output("#{bin}/contig version")
  end
end
