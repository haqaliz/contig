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
  version "0.7.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.7.0/contig-macos-arm64"
      sha256 "6757ec6735e4bd066e1a36c5a2159cba4fa7cca15e6e4031f88a9f780172e8d7"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.7.0/contig-macos-x86_64"
      sha256 "fd5c9f4a0c5402ac47d34a272211a55b9719585361d55a509cb5f53f61c6aaca"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.7.0/contig-linux-x86_64"
    sha256 "a90c831b952b50813b39e71bd272fcdcc73f9ab926af8e3d53e91b685a30a88d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.7.0", shell_output("#{bin}/contig version")
  end
end
