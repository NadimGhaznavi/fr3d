# Journal Tool

The Journal Tool lets Fr3d create and review persisted, timestamped notes stored in MariaDB.

## Input

The journal_tool accepts an operation and returns Markdown. It never exposes database credentials, tables, or general query access.

## Operations

- new_entry requires a title containing 1 to 120 characters and an entry containing 1 to 8,000 characters across no more than five paragraphs.
- list_entries accepts only the operation and an optional limit from 1 to 20. The default limit is 20, and entries are returned newest first.

Titles, entries, operation names, and list limits are validated before the journal is accessed.

## Output

The new_entry operation returns a Markdown confirmation containing the stored entry and its automatically generated date and time. The list_entries operation returns a single Markdown page containing recent entries.

Journal entries remain in MariaDB across upgrades. Uninstalling Fr3d removes the database and its entries.

- [Return to the Knowledge Base](/)
