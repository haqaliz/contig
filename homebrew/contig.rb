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
  version "0.43.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.43.0/contig-macos-arm64"
      sha256 "d99c77066f982836d7ca1403c63f1a4f9085479661988421743f22d1486c9a1b"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.43.0/contig-macos-x86_64"
      sha256 "a88fae2dc312c0f76697e4b8ba889686026b58d85567e82d7bd3034a533d3516"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.43.0/contig-linux-x86_64"
    sha256 "33f1a6eed994919bcfb5b860a6b022d64291482fbf1d293f39f821aeb5ffbb10"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.43.0", shell_output("#{bin}/contig version")
  end
end
