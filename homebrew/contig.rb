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
  version "0.59.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.59.0/contig-macos-arm64"
      sha256 "49e78184295a38695bcfc7c2b1d581d800579f1aecf01091fede2460ef27a2c5"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.59.0/contig-macos-x86_64"
      sha256 "8fa7c58876d423a3251b8ced252907e3c0c7b2d48779ae38f88bc0b4de332b41"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.59.0/contig-linux-x86_64"
    sha256 "26c002e692bf94760ab09b1fdc06aa93ceb0c74afd6c80edf522362a652bfba6"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.59.0", shell_output("#{bin}/contig version")
  end
end