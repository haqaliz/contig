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
  version "0.15.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.15.0/contig-macos-arm64"
      sha256 "9cf4346dfa0f5f18a7702888f35a5806dff274164e16352df4a141e4dc7ebad7"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.15.0/contig-macos-x86_64"
      sha256 "3b5cd963747a48cf2645d76bc2134166227d22a3f25145e10eb3d623dca9839a"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.15.0/contig-linux-x86_64"
    sha256 "4ec8ddf6b2279cab1f1d74afc9e27f717c5d5db08ee9f57b79c0aed90b766ebc"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.15.0", shell_output("#{bin}/contig version")
  end
end
