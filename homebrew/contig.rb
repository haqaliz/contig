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
  version "0.19.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.19.0/contig-macos-arm64"
      sha256 "705a444a608129fec304ad25b4a178f0e1cf8b946f0ab43d0ad8fae655c8a4c4"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.19.0/contig-macos-x86_64"
      sha256 "6c99be1edc73a68c3da3783c9345b12ecc236ce375faa14ec2452632ef79d625"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.19.0/contig-linux-x86_64"
    sha256 "ae35cceaeb0a381358943459295792f6c0a5c8dd8a97397f1f547688874dc4f0"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.19.0", shell_output("#{bin}/contig version")
  end
end
