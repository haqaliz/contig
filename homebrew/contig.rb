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
  version "0.52.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.52.0/contig-macos-arm64"
      sha256 "da9d6738ea71a932dede53da029ac4ab8c92428533dfb91927821f36ed49769a"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.52.0/contig-macos-x86_64"
      sha256 "19d1013aa8285d08d3802b087003b5015b57cdb3398ff42c4bd5cee1eaedffe4"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.52.0/contig-linux-x86_64"
    sha256 "b5a4443b4920ff85c71ee1c2d3a293d0dec790f0862732e02c1f9c793a89cf2d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.52.0", shell_output("#{bin}/contig version")
  end
end
