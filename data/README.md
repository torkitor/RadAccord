# Complete scientific archive

[`RadAccord-1.0.0.zip`](RadAccord-1.0.0.zip) preserves the complete verified
scientific release, including original source, both frozen protocols, all native
outputs, comparison diagnostics, example images and historical validation records.
It is approximately 12.8 MB compressed. The archive is supplied locally; restoring
records does not download anything or contact an extraction-library developer.

SHA-256: `43ff30b546e1904b1f119c6349747d3e6289b273f2b4ee18c80dc57d0b2970bd`.

The GitHub tree keeps source and JSON summaries readable. Large JSONL records
remain compressed because one diagnostic file alone exceeds 240 MB. From the
repository root, restore their exact bytes to their original locations with:

```bash
python -B scripts/restore_records.py
```

The command verifies the archive hash, validates paths, restores only the archived
`work/**/*.jsonl` records, and refuses to replace a different existing record.
Restored records are ignored by Git; retain them locally for reproduction. To
inspect the original distribution itself, extract the ZIP into a separate folder.
All images in the distributed archive are synthetic.
