// Runs once before the whole suite: copy the synthetic run fixtures into the runs
// directory so the dashboard can render them. They are removed again in
// global-teardown, so they never persist in a user's runs folder.
import { installFixtures } from "./fixtures";

export default function globalSetup() {
  installFixtures();
}
