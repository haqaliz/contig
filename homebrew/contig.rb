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
  version "0.31.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.31.0/contig-macos-arm64"
      sha256 "84d8c4f9d09f803ef19414a3af0b52f1697b634011a01e2d530a04ec01e19a2e"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.31.0/contig-macos-x86_64"
      sha256 "cbb8cb27809bef0336af7c2db2d3cae822478ea3954b0a67c851bac99547cec9"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.31.0/contig-linux-x86_64"
    sha256 "a9dc6057442ad0cc7314f7671dcd75c85cd009b1372777645ac1dd441f2c1acd"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.31.0", shell_output("#{bin}/contig version")
  end
end
