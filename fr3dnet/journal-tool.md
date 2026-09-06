# Journal Tool

The Journal Tool lets Fr3d create and browse persisted, timestamped journal entries.

## Write an Entry

Call journal_tool with title and entry. Titles may contain up to 120 characters
and entries up to 10,000 characters. Both must contain text. One entry may be
created per minute across the journal. A successful response includes its ID
and UTC creation time.

## View Entries

Call journal_view_entries with url set to / to begin browsing.

The result is a Markdown page titled Journal Entries with links to the ten newest
entry titles. Follow a link by calling journal_view_entries again with the exact
URL from that link, just as you navigate with the knowledge-base tool.

- An entry URL such as /entries/42 displays its title, UTC date and time, and text.
- Next Page and Previous Page links navigate ten entries at a time.
- The Journal Entries link returns to the newest entries.

Journal URLs belong to journal_view_entries. Do not send them to kb_tool.
Browsing does not create entries or count towards the writing rate limit.
Entries are ordered newest first, with ID breaking timestamp ties. New entries
can shift page boundaries between requests.

Journal entries remain in MariaDB across upgrades. Uninstalling Fr3d removes
the database and its entries.

- [Return to the Knowledge Base](/)
