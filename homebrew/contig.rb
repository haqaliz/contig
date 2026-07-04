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
  version "0.14.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.14.0/contig-macos-arm64"
      sha256 "dc503618fefcd4066954b29d9bce33624804bc788f3fa3c4e34dd52bc186e0ec"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.14.0/contig-macos-x86_64"
      sha256 "0623116551674e1a0d4450c53dfdf09fd523c21ca62a9e4c9887aef3ad6edc9c"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.14.0/contig-linux-x86_64"
    sha256 "11cd3a95e7d17e1be23e4258004bfa79294fd31c88472709cba1e3d4b8fb6e68"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.14.0", shell_output("#{bin}/contig version")
  end
end
