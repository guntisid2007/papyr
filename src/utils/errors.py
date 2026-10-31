"""Turn converter and OS error text into one plain sentence for the window. The raw text stays in Details."""

DAMAGED = "The file appears to be damaged."
NOT_WRITABLE = "The destination folder is not writable."
GENERIC = "This file couldn't be converted."

# Checked in order. A rule matches when every phrase appears in the lower-cased message.
_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("unsupported file type",), "This file format isn't supported."),
    (("password",), "This PDF is password-protected."),
    (("doesn't allow copying",), "This PDF's security settings don't allow its content to be copied, so Papyr "
                                 "won't convert it."),
    (("pdf is encrypted",), "This PDF is protected. Papyr won't copy it into a new PDF, because the copy would "
                            "lose that protection."),
    (("protection scheme",), "This PDF uses a kind of protection Papyr can't open."),
    (("too large",), "This image is too large to convert safely."),
    (("not enough memory",), "There isn't enough memory to convert this file."),
    (("no such file", ".papyr-"), "The Save to folder was moved or deleted."),
    (("no such file",), "The file was moved or deleted."),
    (("could not read", "permission denied"), "Papyr isn't allowed to read this file."),
    (("permission denied",), NOT_WRITABLE),
    (("read-only",), NOT_WRITABLE),
    (("operation not permitted",), NOT_WRITABLE),
    (("no space left",), "There isn't enough free space on the disk."),
    (("file name too long",), "The file's name is too long to save in this folder."),
    (("pdf has no pages",), "This PDF has no pages."),
    (("notebook has no cells",), "This notebook is empty."),
    (("only jupyter notebooks in format 4",), "This notebook uses an old format that Papyr can't read."),
    (("not a valid notebook",), "This isn't a valid Jupyter notebook."),
    (("notebook is damaged",), "This notebook file is damaged."),
    (("notebook could not be laid out",), "Papyr read this notebook but couldn't lay out its pages."),
    (("notebook has no list of cells",), "This notebook file is damaged."),
    (("leaves no room on the page",), "The margins are too large for the page."),
    (("none of the files could be read",), "None of the files could be read."),
    (("could not read",), DAMAGED),
    (("empty file",), DAMAGED),
    (("damaged",), DAMAGED),
    (("corrupt",), DAMAGED),
    (("truncated",), DAMAGED),
    (("cannot identify",), DAMAGED),
    (("eof marker",), DAMAGED),
    (("startxref",), DAMAGED),
    (("stream has ended",), DAMAGED),
)


def friendly_error(message: str) -> str:
    text = message.lower()
    for phrases, friendly in _RULES:
        if all(phrase in text for phrase in phrases):
            return friendly
    return GENERIC
