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
  version "0.34.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.34.0/contig-macos-arm64"
      sha256 "a0217252f96dfa131224e87b2e743c0f319fa1adfcbc20035531db46883c467e"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.34.0/contig-macos-x86_64"
      sha256 "cf79aca9006c08c8a94dff17b0d88865408ab800fa3500f3d744d6cf037df9ae"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.34.0/contig-linux-x86_64"
    sha256 "0ed43cc4fbfaa1f9e26d47267e6f2e1f2ece501106c33056fa6a3406637d7137"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.34.0", shell_output("#{bin}/contig version")
  end
end
