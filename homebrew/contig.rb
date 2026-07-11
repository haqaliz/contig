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
  version "0.30.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.30.0/contig-macos-arm64"
      sha256 "2142b3c9b4fb0b4d1b85b0d40108ca15deea4673fc6b2c1f000ecaefae76bd4c"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.30.0/contig-macos-x86_64"
      sha256 "68f7b128ad23470a8b1e49c0a637a79a59dd06945986914945d8c17f781d1a95"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.30.0/contig-linux-x86_64"
    sha256 "c0dd8e2d933eefbf11efe8ac47eaaa9e8fccab134b4a2ac0d583e2157a5e3bac"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.30.0", shell_output("#{bin}/contig version")
  end
end
