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
  version "0.41.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.41.0/contig-macos-arm64"
      sha256 "264786abbf30737ba9063ec1df2b18b097618e09cb62c9a401ff7edbfc0c4156"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.41.0/contig-macos-x86_64"
      sha256 "4dd883e0c21d2aa4ba14ac3ca483878ece23fffd114c1263b86254a9270957b5"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.41.0/contig-linux-x86_64"
    sha256 "38e8e3441d9b58696b6962083687a4764d7a22c36b4b29085b0742b5a873a362"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.41.0", shell_output("#{bin}/contig version")
  end
end
