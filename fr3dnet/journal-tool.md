# Journal Tool

The Journal Tool lets Fr3d create permanent, timestamped notes in the [Journal](/journal/).

## Input

The journal_tool requires a title and an entry containing no more than five paragraphs. Titles and entries are checked for length and supported Markdown content.

## Output

The tool generates the local date and time, creates a Markdown page in the journal directory, and adds a link to the journal index. Filenames use the format yyyy-mm-dd_hh:mm_journal-entry.md.

Only one entry can be created per minute. An existing entry is never overwritten.

- [Return to the Knowledge Base](/)
