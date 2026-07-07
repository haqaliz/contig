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
  version "0.22.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.22.0/contig-macos-arm64"
      sha256 "26710c8196399684fd958308a611258347bc472897cdd5e83ce4bad3e94b6ccb"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.22.0/contig-macos-x86_64"
      sha256 "d72a508e5caa652029cd122286dc54e1a21537ec527d45c6f02249255898f105"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.22.0/contig-linux-x86_64"
    sha256 "504249a6baaaf6e2ab84609565f34bb5d4d4d484640374c4c1c7589db97bb5f0"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.22.0", shell_output("#{bin}/contig version")
  end
end
