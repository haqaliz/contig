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
  version "0.63.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.63.0/contig-macos-arm64"
      sha256 "5723d3f2d8374819f59092035aafbfa8ab4785f97e4f3c28c6335458545c8026"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.63.0/contig-macos-x86_64"
      sha256 "764eb57808f8d49e7d7e51562f128ed958ef5f1d1129d5df0d5b463748b31737"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.63.0/contig-linux-x86_64"
    sha256 "ace3195ee98e861254db72a978af1d30a51ca88ca83aec2beabc837a52bad5d0"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.63.0", shell_output("#{bin}/contig version")
  end
end