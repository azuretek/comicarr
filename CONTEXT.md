# Comicarr domain context

## Import Inbox

The review queue of discovered files that are not yet durably associated with a Series. Records remain pending until an operator ignores, deletes, edits, or finalizes them.

## Manual import finalization

The operator-confirmed workflow that binds pending Import Inbox records to a Series, places or archives their files, rescans the library, and marks the records imported only after those steps succeed.

## Series

A monitored comic or manga title and its library directory, issues or chapters, metadata, and acquisition state.

## Series provider

Who issued a Series' identifier: ComicVine, MangaDex (`md-` prefix), or MyAnimeList (`mal-` prefix). Distinct from whether the Series is manga — legacy manga rows predate the prefixes and are ComicVine-issued, so the provider answers routing questions while `ContentType` answers content questions. `comicarr/series_kind.py` reconciles the two.

## Chapter source

The MangaDex UUID a manga Series polls for new chapters. MangaDex Series carry it in their ComicID; MyAnimeList Series supply metadata from MAL but keep the chapter source in `MangaDexID`, and have none until it is resolved.

## Log level

Comicarr's single verbosity dial, named by the severity it admits: `0` warning, `1` info, `2` debug. Level `0` means warnings and errors, not silence, which is why it is never called "quiet" — `--quiet` and `--verbose` are flag spellings, not level names.

## Support bundle

A downloadable archive of allowlisted diagnostic data, engineered for public issue attachment after operator review. If its contents appear sensitive, the operator shares it privately with maintainers instead; CarePackage is the legacy implementation name, not the user-facing term.
