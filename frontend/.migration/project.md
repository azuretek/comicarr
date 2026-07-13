# project

2026-07-13, transformation engine for legacy `new-york`; all direct Radix UI imports and dependencies removed.

## Changed

Converted the direct Radix wrappers in `src/components/ui`, `src/components/custom`, and the onboarding dialog to `@base-ui/react`; portal-based overlays now use Base UI Positioner and Popup parts. `npm uninstall` removed the direct `@radix-ui/react-*` dependencies. `rg -n "@radix-ui|radix-ui" src package.json` is clean.

## Left alone

`vaul`, `cmdk`, `sonner`, and `react-day-picker` remain: they are non-Radix libraries. The lockfile retains Radix transitively through `vaul` and `cmdk`.

## Behavior changes

Base UI uses `render` instead of `asChild`, and its animations use transition hooks. Tooltip delay is now mapped to `delay`; menu checkbox/radio close behavior and Base UI's manual tabs activation require browser QA.

## Verify by hand

Open dialogs, sheets, menus, selects, tooltips, and the onboarding flow. Check focus return, Escape/outside dismissal, keyboard navigation/typeahead, and slider keyboard changes.
