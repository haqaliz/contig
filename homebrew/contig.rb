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
  version "0.62.0"

  on_macos do
    on_arm do
      url "https://github.com/haqaliz/contig/releases/download/v0.62.0/contig-macos-arm64"
      sha256 "1e48f445845290bbb8ea50296587dea6a73535076ba34fae67886d78dd5f4fd6"
    end
    on_intel do
      url "https://github.com/haqaliz/contig/releases/download/v0.62.0/contig-macos-x86_64"
      sha256 "3646d8e90bdcdf6c88c8864686685155957532eaf13e00af9bf871904d9e8ab6"
    end
  end

  on_linux do
    url "https://github.com/haqaliz/contig/releases/download/v0.62.0/contig-linux-x86_64"
    sha256 "9228ac1609dc72e242ef9506c7f3269431026aca2bbd36472d63b04f934383c9"
  end

  def install
    bin.install Dir["contig-*"].first => "contig"
  end

  test do
    assert_match "0.62.0", shell_output("#{bin}/contig version")
  end
end