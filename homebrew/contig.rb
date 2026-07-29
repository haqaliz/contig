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
  version "0.49.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.49.0/contig-macos-arm64"
      sha256 "cf2b1453858b0b6ceffc09f6f5ba78e0bcd856ed2ea40df22c3e2be31cad2f16"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.49.0/contig-macos-x86_64"
      sha256 "3423e872fc8382159d128f9b9eaee18c0eb2446182ec73952023ffb91cbb180e"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.49.0/contig-linux-x86_64"
    sha256 "bf6525cd29a3645678afd616b944a0e69ec12f32f95ff1225401e10f7103c33d"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.49.0", shell_output("#{bin}/contig version")
  end
end
