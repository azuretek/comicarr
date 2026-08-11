/** PROTOTYPE — variant keys and labels (kept out of component files for fast refresh). */

export const VARIANT_A_META = {
  key: "A",
  name: "Console first",
} as const;

export const VARIANT_B_META = {
  key: "B",
  name: "Control + table",
} as const;

export const VARIANT_C_META = {
  key: "C",
  name: "General + sheet",
} as const;

export const LOGS_PROTOTYPE_VARIANTS = [
  VARIANT_A_META,
  VARIANT_B_META,
  VARIANT_C_META,
] as const;
