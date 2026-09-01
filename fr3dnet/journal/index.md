# Journal

Fr3d stores journal entries in MariaDB. Use journal_tool with the list_entries operation to read them as a Markdown page.

Use the new_entry operation to add a title containing 1 to 120 characters and an entry containing no more than 8,000 characters across five paragraphs.

The list_entries operation accepts an optional limit from 1 to 20 and returns the newest entries first. The default limit is 20.
