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
  version "0.10.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.10.0/contig-macos-arm64"
      sha256 "460a1d480844c6dcd584056727d9d2cbb752df65581903a388f28ca1c5029726"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.10.0/contig-macos-x86_64"
      sha256 "b0d518cd41049791d7086e68ac2ced3cd81448f428e37caae8ea55c071ed3130"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.10.0/contig-linux-x86_64"
    sha256 "5aecd8740256f9dd508bdc3acf7d022b20a18bfb2b1d30bc82beea5d1d0ca77f"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.10.0", shell_output("#{bin}/contig version")
  end
end
