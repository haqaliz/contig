# Homebrew formula for the contig CLI. This installs the standalone release binary
# (no Python needed). It lives here as the source of truth; the published tap is a
# separate repo, haqaliz/homebrew-contig, where this file goes as Formula/contig.rb.
# After a release builds the binaries, fill in the sha256 values (see RELEASING.md),
# commit to the tap, then: brew install haqaliz/contig/contig.
#
# A real pipeline run still needs Nextflow, a Java runtime, and a container runtime;
# the self-contained commands work without them.
class Contig < Formula
  desc "Agentic bioinformatics analyst: run, self-heal, verify, reproduce engine"
  homepage "https://github.com/haqaliz/contig"
  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v1.2.0/contig-macos-arm64"
      sha256 "6e683b431606e27ffb87e202c62c369501ae838b43efef495f41121a1447e8ef"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v1.2.0/contig-macos-x86_64"
      sha256 "1abe47e981fd499afa17bfb2199d7a51b814ef6c2afaf45263b3d32766807437"
    end
  end

  on_linux do
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v1.2.0/contig-linux-x86_64"
      sha256 "f404583ea0ab830cbe543374ef0228a273c9014af5fda22cc65fda730332eac2"
    end
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "1.2.0", shell_output("#{bin}/contig version")
  end
end
