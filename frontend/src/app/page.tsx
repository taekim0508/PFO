import { existsSync } from "node:fs";
import path from "node:path";
import { IndexApp } from "@/components/IndexApp";
import { site } from "@/lib/site";

// Checked once when the module loads: the résumé is a file in public/, not request data.
const hasResume = existsSync(path.join(process.cwd(), "public", site.resumePath));

export default function Home() {
  return <IndexApp hasResume={hasResume} />;
}
