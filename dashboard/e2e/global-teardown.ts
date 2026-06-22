// Runs once after the whole suite: remove the synthetic run fixtures the global
// setup installed, so they do not linger in the runs directory.
import { removeFixtures } from "./fixtures";

export default function globalTeardown() {
  removeFixtures();
}
