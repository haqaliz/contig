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
  version "0.46.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.46.0/contig-macos-arm64"
      sha256 "73fd3252f82588029a9c3f6c34997cb094e007ee30f2a1de6d5ddd54e451c421"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.46.0/contig-macos-x86_64"
      sha256 "b3f23ef5f4cd47bf6ead596c33bd53eaee6504e34992db60ae387d977dc0022c"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.46.0/contig-linux-x86_64"
    sha256 "2aa0645efbf14bec1eb254cf8c6c41ef985bf0baaddf41ecab057d45acfc64d2"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.46.0", shell_output("#{bin}/contig version")
  end
end
