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
  version "0.12.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.12.0/contig-macos-arm64"
      sha256 "2a4fc7e024742cbf5bdfbbdb7bda23fd6780d2f2f94d0b24ab9d8d1d9c5d4fa8"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.12.0/contig-macos-x86_64"
      sha256 "ee694aa2507f444c19f782fff914110e0e18f938f92a36daf4c5889c5ca5d9ee"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.12.0/contig-linux-x86_64"
    sha256 "2ea4db5f4e72c8d3b92c74b8bc1fe9f5a07bfb367e52d96d166efa09d868fe10"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.12.0", shell_output("#{bin}/contig version")
  end
end
