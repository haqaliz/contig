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
  version "0.56.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.56.0/contig-macos-arm64"
      sha256 "747180d25e80e364361d53054e54291c49bbcbd995c1030e5b98942f77decdf3"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.56.0/contig-macos-x86_64"
      sha256 "1cb5d05153cdb8ec2a524c1d7bb6941baa40db5cabbbd1da12d167d47e24de0d"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.56.0/contig-linux-x86_64"
    sha256 "e118d5052897534cdc7cc3b20071c22b699384c6560cd53e6801f628dfdef602"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.56.0", shell_output("#{bin}/contig version")
  end
end