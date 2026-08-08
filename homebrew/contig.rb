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
  version "0.51.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.51.0/contig-macos-arm64"
      sha256 "cb25cdc3728df6f4caffc70534f696118223cc924d32c6623a49d9ec7af35be3"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.51.0/contig-macos-x86_64"
      sha256 "196dec2635ed69ad52af8631974c38873a1d32de518bb12137a6931f236ffafb"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.51.0/contig-linux-x86_64"
    sha256 "0c47bc960cc31eac5f8e9f13ddf34c69d1aea5915e7408cc0f1021716f7b519d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.50.0", shell_output("#{bin}/contig version")
  end
end
