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
  version "0.53.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.53.0/contig-macos-arm64"
      sha256 "688ba9f5eb145ef68b503af99229571842091ed9509e6a4472b778dec19c9761"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.53.0/contig-macos-x86_64"
      sha256 "e70d639d7307c5723a70318568705f0a43e423c4fe5fd40f160d801b2b4a3000"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.53.0/contig-linux-x86_64"
    sha256 "fe735f49efbdc60da2c255b66d170202ee3f93e81678772fd6a47fb9c0a287c3"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.53.0", shell_output("#{bin}/contig version")
  end
end
