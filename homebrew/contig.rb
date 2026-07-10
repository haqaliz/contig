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
  version "0.28.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.28.0/contig-macos-arm64"
      sha256 "bcf53b0910c14637253713ea776e1c43210cc7e9d142d024df87c25d5303a27b"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.28.0/contig-macos-x86_64"
      sha256 "2aa9fae8b465f1c11c2be46acfcabc75d487be9c01d2a49cb06c8a9659f3134b"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.28.0/contig-linux-x86_64"
    sha256 "825995a7d4e4a173d9061039c1cbd3ffc410c07fe7e4cee14297b19ef3e897c4"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.28.0", shell_output("#{bin}/contig version")
  end
end
