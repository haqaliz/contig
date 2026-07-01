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
  version "0.11.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.11.0/contig-macos-arm64"
      sha256 "0f030b8b9bc1361fd49503fb82d160a16160dae3ef27cc598e590bf48b4655e3"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.11.0/contig-macos-x86_64"
      sha256 "37e641018415de0ff016293119b1ea25d0795fbc094f23a0865d90bd0bc12695"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.11.0/contig-linux-x86_64"
    sha256 "30129d52d4f1fbc2bc5ea5a2a8f9f280a5d1e8738234952872aa6d7902d60181"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.11.0", shell_output("#{bin}/contig version")
  end
end
