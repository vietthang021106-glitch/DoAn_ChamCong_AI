# AI1 Full Test

Bộ kiểm tra độc lập cho ArcFace `buffalo_l`. Nó import `face_engine.py` và `face_matching.py` của AI1, nhưng enrollment/gallery/kết quả chỉ nằm trong thư mục này. Không truy cập DB và không gọi luồng chấm công.

## Quick Start

Mở CMD:

```bat
chcp 65001 >nul
cd /d C:\DoAn_ChamCong_AI
python test_ai1_full\run_test_ai1.py
```

1. Chọn `1`, nhập `MaNV_1`, nhìn lần lượt frontal, left, right, up, down và nhấn SPACE ở từng pose.
2. Lặp lại với ID khác nếu cần.
3. Chọn `2` để build gallery.
4. Chọn `5` để so sánh Single với Multi trên cùng sequence 3 frame.

Nếu dùng benchmark venv đã tạo:

```bat
benchmark_ai1\.venv\Scripts\python.exe test_ai1_full\run_test_ai1.py
```

## Lệnh trực tiếp

```bat
python test_ai1_full\capture_enrollment.py --id MaNV_1
python test_ai1_full\build_gallery.py
python test_ai1_full\test_single_frame.py --expected MaNV_1
python test_ai1_full\test_multi_frame.py --expected MaNV_1
python test_ai1_full\compare_single_multi.py --expected MaNV_1
python test_ai1_full\compare_single_multi.py --expected UNKNOWN
```

Ảnh enrollment đã tồn tại thì tool dừng để tránh ghi đè im lặng. Chỉ thêm `--overwrite` khi muốn chụp lại toàn bộ pose của ID đó:

```bat
python test_ai1_full\capture_enrollment.py --id MaNV_1 --overwrite
```

## Cách hoạt động

- `CameraSource` trả frame OpenCV BGR; hiện có `WebcamSource` (backend MSMF, DSHOW, default; index 0–5). Nhận diện không phụ thuộc nguồn frame.
- Enrollment kiểm tra đúng một mặt, quality gate production, embedding ArcFace hợp lệ 512D/L2 và pose từ `face_engine.estimate_head_pose` cùng bộ phân loại pose AI1 hiện có.
- Gallery giữ riêng 5 embedding mỗi người, không average. `UNKNOWN` không được enrollment.
- Matching dùng cosine và hàm production `face_matching.identify_embedding`, tức MAX similarity qua các sample.
- Multi-frame lấy 3 frame cách nhau khoảng 300 ms, kiểm tra consistency bằng ngưỡng riêng `CONSISTENCY_THRESHOLD`, lấy mean embedding rồi L2 normalize trước khi matching. Consistency threshold không thay threshold nhận diện.
- Ngưỡng nhận diện lấy từ `FACE_RECOGNITION_THRESHOLD` qua helper AI1 hiện tại nếu import được; mặc định production là `0.45`.
- SPACE chạy nhận diện; S lưu ảnh test với tên duy nhất; Q/ESC thoát.
- `results/recognition_results.csv` lưu quyết định và latency, không lưu embedding. Latency tính thời gian xử lý model/matching, không tính thời gian người dùng chờ hoặc khoảng nghỉ giữa các frame.

## Dependencies

Dùng Python có `numpy`, `opencv-python`, `insightface`, `onnxruntime` và các dependency mà AI1 `face_engine.py` cần. Ví dụ cài trong môi trường test riêng:

```bat
python -m pip install numpy opencv-python insightface onnxruntime
```

InsightFace có thể cần tải model `buffalo_l` ở lần khởi tạo đầu. Webcam phải được Windows cho phép.

## Files

```text
test_ai1_full/
├── data/enrollment/<ID>/{frontal,left,right,up,down}.jpg
├── data/captures/
├── gallery/gallery.npz
├── gallery/gallery_meta.json
└── results/recognition_results.csv
```

Chỉ các file pose cần thiết được đưa vào gallery. Ảnh test không được tự động đưa vào enrollment. Tất cả file dữ liệu ở đây là riêng cho tool, không liên quan FaceEmbedding DB production.
