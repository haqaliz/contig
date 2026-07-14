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
  version "0.35.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.35.0/contig-macos-arm64"
      sha256 "3d39e2b3fa64e0904e123ec8c8534301aac538975529958b9e82fda2356dcc09"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.35.0/contig-macos-x86_64"
      sha256 "3d976d5941a191de192ff2a48da2d8ad4a17341f7b149ae18e156fe1bd086cbb"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.35.0/contig-linux-x86_64"
    sha256 "b73003759990f0b9e86cc29afc49c833c8c421968aaa11d823c542a0242ec3c8"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.35.0", shell_output("#{bin}/contig version")
  end
end
