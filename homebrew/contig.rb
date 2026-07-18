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
  version "0.42.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.42.0/contig-macos-arm64"
      sha256 "37cf2d49f30e78aafe7f572ad2ada2b82a14435f4a92595ab518709cee327c2f"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.42.0/contig-macos-x86_64"
      sha256 "9dc9cfe286a50c2152084dd02dfc99f5a660593cdda473a9bcaa4d31389775de"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.42.0/contig-linux-x86_64"
    sha256 "036e88887dba5d46bb863b5749e7baf63c4611a6361711dda555a6717584e2b4"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.42.0", shell_output("#{bin}/contig version")
  end
end
