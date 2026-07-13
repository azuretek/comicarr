# dialog

2026-07-13, transformation engine; migrated to Base UI Dialog.

## Changed

`src/components/ui/dialog.tsx`, sheet wrappers, and onboarding now use Backdrop and Popup; direct Radix scan is clean.

## Left alone

Vaul drawer remains untouched.

## Behavior changes

Animations now use Base UI transition hooks.

## Verify by hand

Open a dialog and sheet; confirm focus return and Escape behavior.
