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
  version "0.32.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.32.0/contig-macos-arm64"
      sha256 "74b7a424d55d7cd1216bcc28966bd50673bc888192f062ae2738b98c42236e8c"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.32.0/contig-macos-x86_64"
      sha256 "ccdf576a0a5002a1365b0533d69c979ac9e8228382a827a7d4f95cdc5c53c0b8"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.32.0/contig-linux-x86_64"
    sha256 "fe69060da2c7bb195e69660d8ad7662690825e3120a5a8d482277404902d03b8"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.32.0", shell_output("#{bin}/contig version")
  end
end
