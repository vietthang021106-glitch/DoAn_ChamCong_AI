# AI1 runtime notes

AI1 continues to use InsightFace `buffalo_l`, the existing 512D L2-normalized
ArcFace vectors, cosine similarity, and MAX over each employee's individual
FaceEmbedding samples. The Python AI service keeps a validated in-memory
gallery; PHP remains the only MariaDB owner.

## Camera source

The Flask camera owner publishes one shared latest-frame pump. Preview,
enrollment, and AI1 recognition read from that source; no other production
module opens a webcam directly. On Windows, webcam selection checks indexes
0 through 5 and tries MSMF, DirectShow, then the default OpenCV backend. The
requested resolution is 640x480. Frames older than 0.75 seconds are rejected.

For an ESP32-CAM MJPEG stream, configure the Flask process environment before
starting it:

```text
AI1_CAMERA_SOURCE=esp32
AI1_ESP32_STREAM_URL=http://esp32cam.local:81/stream
```

The stream reader reconnects after errors, decodes JPEG SOI/EOI frames in a
background worker, and exposes only fresh decoded frames. A custom HTTP(S)
stream URL can be used in `AI1_ESP32_STREAM_URL`.

## Enrollment safety

The web enrollment flow stages `frontal`, `left`, `right`, `up`, and `down`
samples in the PHP session. It requires eight consecutive valid pose frames,
checks detection and image quality, and counts only increasing frame sequence
numbers from the shared camera owner. It compares every captured vector with
the frontal reference. The complete batch is revalidated before one database
transaction replaces the previous samples. The transaction checks the
employee's gallery revision; a concurrent change returns a conflict. An exact
retry after a lost response returns the already saved sample IDs instead of
inserting a duplicate batch.

The legacy Flask enrollment writer is disabled; the Flask page links to the
PHP/MariaDB employee flow. Single-frame identify/verify routes return a retry
response. The legacy camera-identify route now only starts the central session.

## Recognition sessions

The Admin scan flow captures three distinct, fresh camera sequence numbers
with at least 250 ms between snapshots. Each snapshot must contain exactly one
face and a valid embedding. Pairwise cosine consistency must meet
`FACE_TEMPORAL_CONSISTENCY_THRESHOLD` (default `0.60`). AI1 selects the frame
with the highest face-crop Laplacian variance, then uses that one embedding
with the existing five-sample MAX matcher and
`FACE_RECOGNITION_THRESHOLD` (default `0.45`). It never averages embeddings.

The scan UI displays MATCH, UNKNOWN, or RETRY. This scan is read-only and does
not write attendance. Existing attendance evidence behavior is unchanged.

Recognition start/best/end snapshots can optionally be saved atomically by
setting `AI1_EVIDENCE_DIR` to a local directory. With the setting empty (the
default), those optional files are not persisted. No raw embedding vectors are
written to logs.
