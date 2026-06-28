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
  version "0.5.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.5.0/contig-macos-arm64"
      sha256 "f52a909437142386f161d19a3c350af7d3795ad9bd62759a974d43d184fd062d"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.5.0/contig-macos-x86_64"
      sha256 "a1ee20e2d63eef62952dbace8d0f43957953a204f01e00adf3f08638adbb4282"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.5.0/contig-linux-x86_64"
    sha256 "95d24146b93221884574a294faeb7e7426ff9ee05476ec5caeaf9d68bbed9daa"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.5.0", shell_output("#{bin}/contig version")
  end
end
