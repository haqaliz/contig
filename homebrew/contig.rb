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
  version "0.1.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.1.0/contig-macos-arm64"
      sha256 "f2345cc041699d32e54f4abf7754cc2ca8cd2667c0a26a868de4d0023a0b5714"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.1.0/contig-macos-x86_64"
      sha256 "5e77a07c9b60c42ad056af910aa0508975593250e0f056d8c6688757f2503e4e"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.1.0/contig-linux-x86_64"
    sha256 "5282b7a3f87fa4fd2f6e9e12478384032334f2c4d87bc8bec8f608f593e7eb00"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/contig version")
  end
end
