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
  version "0.55.1"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.55.1/contig-macos-arm64"
      sha256 "a71b2ce38797a72515c19f13cab6f9ad1f46c94b56d3dcce0582a6d395ca2d6d"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.55.1/contig-macos-x86_64"
      sha256 "da46cbd8dcfa9e1d783dee9452ea8ef3e1de44b7b1c6b3c1d1de737f55070b80"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.55.1/contig-linux-x86_64"
    sha256 "ee4e4dac2a8ac598d9fa99cf756afb1ea5e2beb5fd45f2f1665828e745136046"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.55.1", shell_output("#{bin}/contig version")
  end
end
