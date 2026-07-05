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
  version "0.17.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.17.0/contig-macos-arm64"
      sha256 "ade91ac2869ef403dba2fe860f28dfc149a6611450443cc63f51415a2a685577"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.17.0/contig-macos-x86_64"
      sha256 "56911c0b2379f254f38ef073e9b98f25e565b5cc4b7d62c3bdbd374219be566e"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.17.0/contig-linux-x86_64"
    sha256 "303740e33aeaf106adff9e5fd374ade9c5a1669596d613772da04ca5a13461ca"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.17.0", shell_output("#{bin}/contig version")
  end
end
