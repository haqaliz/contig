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
  version "0.36.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.36.0/contig-macos-arm64"
      sha256 "162a8b4a822274cc57b8d8a385d27c010950e41f12d364e3fefd17572ddeb60c"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.36.0/contig-macos-x86_64"
      sha256 "05a5400719d3d1d0037975ed9170e9bad2d295a387f45419a216527fb33a2aeb"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.36.0/contig-linux-x86_64"
    sha256 "1e1264dc0fdf76ef788821ad7b3b474c9fb6f7ff0a1744c1952a76375332fe38"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.36.0", shell_output("#{bin}/contig version")
  end
end
