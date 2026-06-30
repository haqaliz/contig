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
  version "0.8.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.8.0/contig-macos-arm64"
      sha256 "75c7772d5cf74853ee8d419d422a0287428a3ff04df6255b9425753be64e2d08"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.8.0/contig-macos-x86_64"
      sha256 "0d1f13a7036c374cf469904b1bdafa79d97c8fb56eb7f8bf314e36faa4eeed0b"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.8.0/contig-linux-x86_64"
    sha256 "af00bb44ddf1515ce75b15a401a18a976b6d5ecc35e5296383049db22faed90d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.8.0", shell_output("#{bin}/contig version")
  end
end
