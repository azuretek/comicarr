import type { ReleaseNotesSection } from "@/types/version";

export function countBullets(sections: ReleaseNotesSection[]): number {
  return sections.reduce((n, s) => n + s.bullets.length, 0);
}
