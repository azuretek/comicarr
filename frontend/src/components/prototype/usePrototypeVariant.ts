import { useSearchParams } from "react-router-dom";
import type { PrototypeVariantMeta } from "./PrototypeSwitcher";

export function usePrototypeVariant(
  variants: PrototypeVariantMeta[],
  param = "variant",
): string {
  const [searchParams] = useSearchParams();
  const keys = variants.map((v) => v.key);
  const raw = searchParams.get(param);
  if (raw && keys.includes(raw)) return raw;
  return keys[0] ?? "A";
}
