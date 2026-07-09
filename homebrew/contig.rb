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
  version "0.24.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.24.0/contig-macos-arm64"
      sha256 "6a5e6c6fd74c7ac1407f7239585bbd745f1f91e506d04f46f4fadf0c1b6f8e1a"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.24.0/contig-macos-x86_64"
      sha256 "eb110d77aa6e44e5016ad6d15885c30541ac1d8a2f997aca1b5d852189d86ab1"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.24.0/contig-linux-x86_64"
    sha256 "6a3a0b5fbb59a45aa365ee60b8e2af1685a4f535ec83995bc3e56ca1033fb442"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.24.0", shell_output("#{bin}/contig version")
  end
end
