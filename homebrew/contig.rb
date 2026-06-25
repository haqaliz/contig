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
  version "0.3.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.3.0/contig-macos-arm64"
      sha256 "d950984eb63db4de51978d4c91beada11934243122294d85455020464c0b8cec"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.3.0/contig-macos-x86_64"
      sha256 "8894520e6675e5d83f41d54e3eeb07eb1416ada9d8a030bdada138c7d4432c3d"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.3.0/contig-linux-x86_64"
    sha256 "ee16908ccb9a143281ffbe7563012e2359caa6e660b0275913073bda1931f55a"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.3.0", shell_output("#{bin}/contig version")
  end
end
