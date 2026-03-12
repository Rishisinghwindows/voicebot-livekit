Knowledge Base — File-based Knowledge Loading
================================================

Drop .txt or .pdf files into this directory and the voice agent
will automatically load their content into the system prompt
at the start of each call.

Supported formats:
  - .txt  — plain text (loaded as-is)
  - .pdf  — extracted via PyPDF2 (install: pip install PyPDF2)

Files are loaded in alphabetical order. Each file's content is
prefixed with its filename for clarity.

Example usage:
  - product_faq.txt      — paste your product FAQs
  - return_policy.txt    — company return/refund policy
  - company_info.pdf     — brochure or documentation

You can also paste knowledge directly in the admin panel
(System Prompt > Knowledge Base textarea) — both sources
are combined automatically.
