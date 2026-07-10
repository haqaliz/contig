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
  version "0.29.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.29.0/contig-macos-arm64"
      sha256 "4e8ae16c1557e23a6a8ba8fc97def9bcfe62096daae67289f646632a4612c064"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.29.0/contig-macos-x86_64"
      sha256 "6cdd340e122b9dcb0645a4a3f7965c5304f1e7d5c9e641afe4fcdad63ebee75e"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.29.0/contig-linux-x86_64"
    sha256 "d88c700623747b658bdd38cdaeff3c5509ff157286a981b94b6267d07fdc9347"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.29.0", shell_output("#{bin}/contig version")
  end
end
