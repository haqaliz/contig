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
  version "0.54.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.54.0/contig-macos-arm64"
      sha256 "eb85f7ade6157225c65ef83d4fea045f01b19c48187a087f161b5a396e3f4c48"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.54.0/contig-macos-x86_64"
      sha256 "265aa820d4446c3fda45caa488493c6da79b936809727b776025e68e19fd6717"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.54.0/contig-linux-x86_64"
    sha256 "7c024916891746dbba58fb8a2a512612fc68fd5c30d2e81edceeb052f4d702f3"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.54.0", shell_output("#{bin}/contig version")
  end
end
