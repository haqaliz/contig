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
  version "0.48.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.48.0/contig-macos-arm64"
      sha256 "e9930dad81285dcae4dc8ca19a6e4ca897a9b3cd0c9773e5a0c93fae9551217f"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.48.0/contig-macos-x86_64"
      sha256 "747669063c7d1d59d21d98533ad7219bf7724ff7eb96699dd6c6b7d309cb3746"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.48.0/contig-linux-x86_64"
    sha256 "fe6fc9369a7d9401378ab5093f19e830931206e874a6c9b613531114b5509791"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.48.0", shell_output("#{bin}/contig version")
  end
end
