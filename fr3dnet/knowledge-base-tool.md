# Knowledge Base Tool

The Knowledge Base Tool gives Fr3d read-only access to the Markdown documentation stored in fr3dnet.

## Input

The kb_tool accepts an internal URL. Use / for the homepage, a trailing slash for a section index, or a page URL without the .md extension.

URLs are checked to prevent path traversal, external links, query strings, fragments, and access outside the documentation root.

## Output

The tool returns the validated Markdown content of the requested page. Begin at / when the location of specific information is unknown.

- [Return to the Knowledge Base](/)
