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
  version "0.61.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.61.0/contig-macos-arm64"
      sha256 "16223ad6182c91bce507e30835e4fabf8c528eeff3c1e624f3a39c4d4fd18de7"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.61.0/contig-macos-x86_64"
      sha256 "f1064bca9b1b10edd22821636cf5bbc737ff3f0f833f54807b4bd3657c57dcf9"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.61.0/contig-linux-x86_64"
    sha256 "779bdd6c69cc47c0c21f7dd9a3b88f6d0a47d8144cc226348caf5a034133ed50"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.61.0", shell_output("#{bin}/contig version")
  end
end