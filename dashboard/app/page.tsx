import { redirect } from "next/navigation";

// The dashboard opens on the run list.
export default function Home() {
  redirect("/runs");
}
