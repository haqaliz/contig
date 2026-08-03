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
  version "0.50.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.50.0/contig-macos-arm64"
      sha256 "d49a916de03cde4a9fbe708d4d56a860c1d6e74a0b855894c9ca3429f3203d2b"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.50.0/contig-macos-x86_64"
      sha256 "3ca7c8f24d8da6b9753e4a7137363bbe95ced4d107db6df45677e6c25f28969c"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.50.0/contig-linux-x86_64"
    sha256 "22a686e234fcbc173b72ba514122069eaa8657156046236c37b8c71c2e9c0e7e"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.50.0", shell_output("#{bin}/contig version")
  end
end
