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
  version "0.13.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.13.0/contig-macos-arm64"
      sha256 "e22d21b2b29c64ee23d7b027cbf8fa33fd59a2d9a441516af04bfffcbfd7d375"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.13.0/contig-macos-x86_64"
      sha256 "3ad7270ee25379f18fa6425df01f6ff5e437781b8616406e61c0a76b3c2937e8"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.13.0/contig-linux-x86_64"
    sha256 "ebb4c23a5f13aef84f6a77820d29ff8d5b9a4731c010c0e3e86be41fc8745160"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.13.0", shell_output("#{bin}/contig version")
  end
end
