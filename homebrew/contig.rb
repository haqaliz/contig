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
  version "0.21.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.21.0/contig-macos-arm64"
      sha256 "4bc53000b5d9aadada13a032b794bee8a1a23c11e735d8bc5d76d38c8cb31c03"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.21.0/contig-macos-x86_64"
      sha256 "2b2fbdf28f5b5a580212680bf1cd1347fe093b09c24bcc1c9834d68629d460f9"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.21.0/contig-linux-x86_64"
    sha256 "5d5d83bd38a85a734f91cf8490b4a56d2501f2e1e8d0d68159f0284518e0f504"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.21.0", shell_output("#{bin}/contig version")
  end
end
