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
  version "0.38.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.38.0/contig-macos-arm64"
      sha256 "7b83d408c2389fe747933eb94dd521883858b2c6ab51cc2859befcf5255fbeba"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.38.0/contig-macos-x86_64"
      sha256 "707091f44dad187c243b6611447b31e7b7e32fef2f032cf1df01c47075775868"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.38.0/contig-linux-x86_64"
    sha256 "4d9f97f2dbf27be3a2bcd9d1e3f9924faaee07839aeeed87527d2f57a59054bf"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.38.0", shell_output("#{bin}/contig version")
  end
end
