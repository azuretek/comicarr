# accordion

2026-07-13, transformation engine; migrated to Base UI Accordion with Panel content.

## Changed

`src/components/ui/accordion.tsx` now imports `@base-ui/react/accordion`; its leftover Radix scan is clean.

## Left alone

Consumer layout and content were retained.

## Behavior changes

Panel animation uses Base UI transition hooks.

## Verify by hand

Open and close an accordion using mouse and keyboard.
