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
  version "0.26.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.26.0/contig-macos-arm64"
      sha256 "a00b7269598168d07f34b96549d2c59d58cfdf0466a969067d4ccb525b0127c2"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.26.0/contig-macos-x86_64"
      sha256 "758385fea26d100013f98400a9cbe03339a3c29d1d7ef6680a2e3a806f28ca53"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.26.0/contig-linux-x86_64"
    sha256 "87fdf44b4edbfb4f87f513d9c508307117616862c42c641ece7e94cb35e48c42"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.26.0", shell_output("#{bin}/contig version")
  end
end
