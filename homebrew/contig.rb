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
  version "0.4.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.4.0/contig-macos-arm64"
      sha256 "5f8f79c54f7e6011365036b8122d09923371f1bfee5ea2628f6d6dc6d35d86c4"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.4.0/contig-macos-x86_64"
      sha256 "de990b7fe1660b9b67984401ef6dc4e90327339b9ca4e05424cb0f7e34a8e3b4"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.4.0/contig-linux-x86_64"
    sha256 "5a4136c205add1109b7639aa67b91b8d70cf246a3b5f7280518594ce793f6111"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.4.0", shell_output("#{bin}/contig version")
  end
end
