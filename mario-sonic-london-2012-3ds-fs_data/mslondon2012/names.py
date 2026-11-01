"""names.csv: human names for fs_data.cpk entries (file number -> name)."""
import os

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "names.csv")


def load_names(path=DEFAULT):
    """{file_number: (name, confidence, note, check)}.

    Lines: number;name;confidence;note;check. 'check' (optional) is the first
    waveform name of that ACB, in sorted order, as derived from its cues
    (see report.txt); it lets the sorter detect a game version where the
    numbering differs.
    """
    names = {}
    if not path or not os.path.isfile(path):
        return names
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = (line.split(";") + ["", "", "", ""])[:5]
            try:
                names[int(parts[0])] = tuple(x.strip() for x in parts[1:5])
            except ValueError:
                pass
    return names
