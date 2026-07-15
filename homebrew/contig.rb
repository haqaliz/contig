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
  version "0.37.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.37.0/contig-macos-arm64"
      sha256 "911b661a9295742b2768d0b19d4d2cc2e91bdbcb2d79ff27bb30ce100e41c717"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.37.0/contig-macos-x86_64"
      sha256 "fb36340aa9d20d4541818f10bd3b9b40dc2c3910711f00a4830530212c916214"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.37.0/contig-linux-x86_64"
    sha256 "e17dc2c29bd808f5bebee0665706ff5e2daac8289ea8e0f9ac7aa89258ff0866"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.37.0", shell_output("#{bin}/contig version")
  end
end
