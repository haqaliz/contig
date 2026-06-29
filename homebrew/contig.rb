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
  version "0.6.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.6.0/contig-macos-arm64"
      sha256 "a3ac27992b2453593c875574d1195d892d5ca891e7ac49bb0caba5f9cd485e1d"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.6.0/contig-macos-x86_64"
      sha256 "797d935e66bfab022ed12cc25eefe6d396e93fbef3d31b29b0e7eb6337483a1c"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.6.0/contig-linux-x86_64"
    sha256 "cad775cea231071418c4782d978dae2f8b3c100686a8806aa4671fef772d1070"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.6.0", shell_output("#{bin}/contig version")
  end
end
