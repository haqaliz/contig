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
  version "0.18.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.18.0/contig-macos-arm64"
      sha256 "0efca34ded26ee1cd89c5a6d7ce7c2e8449be2496f86de06379ef26542bc6d6e"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.18.0/contig-macos-x86_64"
      sha256 "6f1b278a2ccc09ef341e5a6b3a13b04648c39f1cf4cdb0d94e5b57dc9a26570f"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.18.0/contig-linux-x86_64"
    sha256 "07868210baa6fa48dc9d761c33f3be4757c57f5bc7aa7061a3dab73fa03d519a"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.18.0", shell_output("#{bin}/contig version")
  end
end
