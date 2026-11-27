# AI1 duplicate-face calibration

The enrollment duplicate check compares Buffalo-L 512D vectors with cosine
similarity and uses the maximum score over every pair in two five-pose sets
(max-over-5x5). It is separate from attendance recognition and does not reuse
the attendance threshold.

## Labeled image layout

Collect at least two independent five-pose enrollment sessions per identity.
Use consented images from different sessions; do not use the same image as both
the stored enrollment sample and an independent recognition test.

```text
calibration-data/
  person-001/
    session-2026-01/
      frontal.jpg
      left.jpg
      right.jpg
      up.jpg
      down.jpg
    session-2026-02/
      frontal.jpg
      left.jpg
      right.jpg
      up.jpg
      down.jpg
  person-002/
    ...
```

The current minimum validation protocol is 10 identities, 30 same-person
session pairs, and 100 different-person session pairs. Those are minimum sample
counts, not an accuracy claim. The operator must choose acceptable FMR/FNMR
targets from the project requirements; the tool deliberately has no default
targets and invents no threshold.

## Run calibration

Use the production Python environment with InsightFace buffalo_l available:

```powershell
python tools/calibrate_face_duplicate_threshold.py `
  --dataset C:\path\to\labeled-calibration-data `
  --output storage\face_duplicate_calibration.json `
  --max-fmr <owner-selected-rate> `
  --max-fnmr <owner-selected-rate>
```

The tool extracts embeddings with the existing `FaceRecognitionEngine`, checks
one face and the production enrollment quality gate for each image, evaluates
same-person and different-person session pairs, and writes aggregate metrics
plus a SHA-256 dataset fingerprint. It never reads the employee database and
never writes employee images or vectors to the report. An insufficient dataset
or targets that cannot both be met produces `validated: false` and a nonzero
exit status.

After reviewing a validated report, copy its exact threshold into the local
`.env` and point PHP to the report:

```dotenv
AI1_DUPLICATE_FACE_THRESHOLD=<exact threshold from report>
AI1_DUPLICATE_FACE_THRESHOLD_VALIDATED=1
AI1_DUPLICATE_FACE_MODEL=buffalo_l
AI1_DUPLICATE_FACE_AGGREGATION=max_5x5_cosine
AI1_DUPLICATE_FACE_CALIBRATION_REPORT=storage/face_duplicate_calibration.json
```

The PHP front controller loads the project `.env` on each request while values
already supplied by the PHP process take precedence. Restart the PHP server
after changing process-level environment variables. The report and threshold
must match; PHP also checks the report format, dataset fingerprint syntax,
minimum counts, model, aggregation, and measured FMR/FNMR before allowing a
comparison against another employee. Until a real labeled calibration is
available, duplicate checks against a non-empty employee gallery remain
fail-closed. An empty gallery is a valid `CLEAR` case.
