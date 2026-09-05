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
  version "0.57.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.57.0/contig-macos-arm64"
      sha256 "ff21f91933dae0d8a01d010477d46dbba9dc9e2db2b273242e674806e48bde8e"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.57.0/contig-macos-x86_64"
      sha256 "b2c835479c1c938190c13612cefa5f571d02c5766361cda486525d3a4686a38a"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.57.0/contig-linux-x86_64"
    sha256 "fc2cd0f7a2da0042b0087ab65a184842190ab740f996c28b3c65817ecc85ffab"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.57.0", shell_output("#{bin}/contig version")
  end
end