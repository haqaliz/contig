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
  version "0.2.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.2.0/contig-macos-arm64"
      sha256 "3613cf983b0de8631aa0543cc155a7cfd5d9230fd24f0e9345505a67dbc8267b"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.2.0/contig-macos-x86_64"
      sha256 "e142659b242e18c8c1946188cd682b2db0ec8d4301fcf676bcf34a28937b24f4"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.2.0/contig-linux-x86_64"
    sha256 "18416d0b0e15c6f9288a7eab75f30784a1836769b4b18aa86bca08b52181259a"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.2.0", shell_output("#{bin}/contig version")
  end
end
