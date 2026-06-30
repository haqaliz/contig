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
  version "0.9.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.9.0/contig-macos-arm64"
      sha256 "0d8f65e998198beaf9539a7f05458a722d80f13dff229e87c68d92eaa8c1ef82"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.9.0/contig-macos-x86_64"
      sha256 "b666c7bd72bbf8270179163d3e9a419f4f6ade5103ba43cf309a5ee99a445faf"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.9.0/contig-linux-x86_64"
    sha256 "c8280d6db1e9e15f6f845d5fa6438de7000ae48948110b7aae006ad6b48bb551"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.9.0", shell_output("#{bin}/contig version")
  end
end
