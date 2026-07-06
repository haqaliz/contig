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
  version "0.20.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.20.0/contig-macos-arm64"
      sha256 "f502d78be12655fcbd76d764dc14115311afe627cd43d8fae41055623c431f15"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.20.0/contig-macos-x86_64"
      sha256 "9b804cd789e56b5f69a0d60ce795e65a932ef0b2c7e9e3f522c9aad3d102a2a3"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.20.0/contig-linux-x86_64"
    sha256 "c8636771e808ce8eb3e860d1f92bbe1ae8c178accaa820fd76497d0fa9713d58"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.20.0", shell_output("#{bin}/contig version")
  end
end
