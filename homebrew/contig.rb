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
  version "0.44.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.44.0/contig-macos-arm64"
      sha256 "7cb4cba3a244c2d2831904dfb3f905c172d3dbf21450422c134443b7d53047ec"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.44.0/contig-macos-x86_64"
      sha256 "225a24164a736a8cd59f6ae39bdafae4c572af997c9258a713216f475930b4b6"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.44.0/contig-linux-x86_64"
    sha256 "4acaf03668e450b3ed11457ea3f971251ed0f95b9186ad947240c805dd98eaec"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.44.0", shell_output("#{bin}/contig version")
  end
end
