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
  version "0.39.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.39.0/contig-macos-arm64"
      sha256 "8d5415127009bf0f93e6b8e548674fd730704750b17ab7522207ee173d0ebc51"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.39.0/contig-macos-x86_64"
      sha256 "abc086175ae9cc308c90e7904c1561f7ce3dffb4b6f1cee4277035ab8c54df0a"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.39.0/contig-linux-x86_64"
    sha256 "b3456586b9348d1bae445783fe6613d8e1e8565ba29617442570cbefbeee1831"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.39.0", shell_output("#{bin}/contig version")
  end
end
