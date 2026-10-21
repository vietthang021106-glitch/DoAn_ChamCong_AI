# BÁO CÁO CHỨC NĂNG HỆ THỐNG CHẤM CÔNG VÀ THEO DÕI SỨC KHỎE

## 1. Tổng quan hệ thống

Hệ thống phục vụ quản lý nhân viên, phân ca, ghi nhận giờ vào/ra và tra cứu lịch sử sức khỏe, cảnh báo. Quản trị viên quản lý dữ liệu chung; nhân viên xem thông tin của mình. Nhận diện khuôn mặt nhằm cung cấp danh tính cho nghiệp vụ chấm công.

Luồng tổng thể là: tạo nhân viên và tài khoản → đăng ký khuôn mặt → phân ca → chấm công vào → làm việc, theo dõi sức khỏe/trạng thái → chấm công ra → tra cứu lịch sử. Tuy nhiên, chuỗi quét mặt rồi tự động chấm công chưa được nối hoàn chỉnh trong source hiện tại.

Báo cáo đối chiếu mã nguồn local ngày 15/10/2026. Web PHP sử dụng MariaDB; Flask cũ vẫn truy cập SQL Server, còn dịch vụ AI Python riêng trao đổi với PHP. “Đã triển khai” trong báo cáo chỉ phần có mã xử lý, không đồng nghĩa đã kiểm chứng vận hành trên thiết bị thật.

## 2. Quản lý nhân viên, tài khoản và phân quyền

Người dùng nhập tên đăng nhập và mật khẩu. Hệ thống tìm tài khoản, liên kết hồ sơ nhân viên và vai trò, rồi xác minh mật khẩu. Nếu hợp lệ, Web tạo phiên đăng nhập mới, lưu mã nhân viên, tài khoản và vai trò vào Session. Mật khẩu không được lưu trong Session. Đăng xuất hủy phiên truy cập.

Quản trị viên được quản lý nhân viên, ca và dữ liệu chung; nhân viên được truy cập trang cá nhân. Việc kiểm tra quyền thực hiện phía máy chủ. Các thao tác thay đổi dữ liệu qua biểu mẫu PHP còn kiểm tra mã CSRF để hạn chế yêu cầu giả mạo.

Khi thêm nhân viên, quản trị viên nhập họ tên, vai trò, tên đăng nhập và mật khẩu. Hệ thống kiểm tra dữ liệu, tên đăng nhập trùng và xác nhận mật khẩu. Hai bản ghi `NhanVien`, `TaiKhoan` được tạo trong cùng transaction: nếu tạo tài khoản lỗi, toàn bộ thao tác rollback, tránh để lại hồ sơ nhân viên mồ côi.

Mật khẩu tạo mới được băm bằng `password_hash`; tài khoản cũ còn có cơ chế kiểm tra tương thích. Khi sửa hồ sơ, quản trị viên có thể đổi thông tin, tên đăng nhập và đặt mật khẩu mới; để trống mật khẩu thì giữ giá trị cũ. Danh sách hỗ trợ tìm nhân viên và xem tình trạng tài khoản, số mẫu khuôn mặt.

## 3. Đăng ký khuôn mặt lần đầu

Nhân viên mới chưa có bản ghi `FaceEmbedding`. Quản trị viên chọn nhân viên để bắt đầu phiên đăng ký. Web kiểm tra nhân viên tồn tại và mô hình AI sẵn sàng; các mẫu thu được tạm giữ trong Session, chưa ghi ngay vào cơ sở dữ liệu.

Source hiện quy định năm tư thế theo thứ tự:

1. Chính diện.
2. Nghiêng trái.
3. Nghiêng phải.
4. Ngẩng nhẹ.
5. Cúi nhẹ.

Ở mỗi bước, frame từ camera được gửi đến AI để phát hiện khuôn mặt, yêu cầu đúng một người và kiểm tra hướng đầu. Không có mặt, nhiều mặt, sai hướng hoặc không ước lượng được tư thế thì chưa chấp nhận mẫu. Khi đúng hướng đủ ổn định, hệ thống chụp và kiểm tra lại frame dùng để lưu.

AI sử dụng InsightFace `buffalo_l`, chạy CPU, để trích xuất embedding ArcFace pretrained 512 chiều. Đây là vector đặc trưng dùng so sánh khuôn mặt, không phải ảnh và không phải quá trình tự huấn luyện ArcFace. Ảnh của mẫu được giữ riêng cùng vector tương ứng.

Đủ năm mẫu hợp lệ, Web mới lưu cả bộ vào `FaceEmbedding`. Mỗi bản ghi gồm `MaEmbedding`, `MaNV`, `VectorData`, `AnhKhuonMat`, `SoChieu`, `ThoiGianTao`. Một nhân viên có nhiều mẫu để biểu diễn khuôn mặt ở các góc khác nhau. Dữ liệu vector và ảnh được kiểm tra trước khi ghi; phiên chưa đủ mẫu không được hoàn tất.

## 4. Đăng ký lại khuôn mặt

Luồng PHP đã có đăng ký lại: giữ bộ mẫu cũ trong lúc thu năm mẫu mới. Sau khi bộ mới hợp lệ, hệ thống xóa mẫu cũ và chèn bộ mới trong cùng transaction. Nếu ghi lỗi, rollback khôi phục dữ liệu trước đó; hủy phiên thu mẫu không làm mất bộ đang lưu.

Sau khi lưu, Web yêu cầu AI tải lại danh sách mẫu. Kết quả lưu dữ liệu và làm mới danh sách được trả riêng, nên lưu thành công chưa bảo đảm AI đã nhận bộ mới. Luồng Flask cũ chỉ cho đăng ký lần đầu, chưa có cơ chế thay thế tương đương.

## 5. Quản lý ca và phân ca

Ca làm việc gồm tên, giờ bắt đầu, giờ kết thúc và trạng thái sử dụng. Quản trị viên có thể tạo, sửa, ngừng sử dụng, kích hoạt lại hoặc xóa ca chưa được tham chiếu bởi phân ca hay chấm công. Ca ngừng sử dụng không được chọn cho phân ca mới nhưng vẫn giữ lịch sử.

Nếu ca đã có chấm công, hệ thống cho đổi tên nhưng khóa thay đổi giờ bắt đầu/kết thúc. Quy tắc này tránh làm thay đổi cách đánh giá đi trễ, về sớm của dữ liệu cũ. Ca mới phải kết thúc sau giờ bắt đầu; hiện chưa hỗ trợ ca qua đêm.

Phân ca là liên kết nhân viên + ca + ngày làm việc trong `PhanCaNhanVien`. Ràng buộc duy nhất bảo đảm một nhân viên có một phân ca mỗi ngày; lưu lại tổ hợp nhân viên/ngày có thể cập nhật sang ca mới. Việc hủy phân ca bị chặn nếu ngày đó đã có chấm công. Khi chấm công, hệ thống tìm phân ca đúng ngày; không có thì từ chối ghi nhận.

## 6. Quét mặt và quy trình chấm công

Phần nhận diện đã có source: ảnh → phát hiện mặt → embedding → so sánh cosine → trả mã nhân viên hoặc không nhận diện được. Khi nhận diện, nhiều mẫu được tổng hợp thành vector đại diện cho từng người; hệ thống lấy điểm cao nhất và so với ngưỡng cấu hình, mặc định 0,45. Đây chưa phải ngưỡng đã được chứng minh phù hợp với dữ liệu thực tế.

Điểm cần phân biệt là API nhận diện chỉ trả kết quả, không tự ghi chấm công. API chấm công hiện nhận `MaNV` từ bên gọi, chưa bắt buộc kết quả xác minh khuôn mặt. Vì vậy, quy tắc “không khớp thì không chấm công” còn cần hoàn thiện ở bước nối hai chức năng.

Ví dụ NV001 được phân ca 08:00–17:00. Sau khi danh tính được cung cấp cho nghiệp vụ, hệ thống kiểm tra nhân viên, phân ca và bản ghi trong ngày:

**Lần thứ nhất — check-in:** Chưa có bản ghi thì tạo `ChamCong`, lưu `MaNV`, `MaCa`, `MaTB`, `GioVao` và `AnhVao` nếu lấy được ảnh; `GioRa` để NULL. Vào 07:55 hoặc đúng 08:00 được đánh giá đúng giờ; 08:10 là đi trễ. Code không có khoảng thời gian cho phép đi muộn.

**Lần thứ hai — check-out:** Đã có `GioVao`, chưa có `GioRa` thì cập nhật giờ ra và `AnhRa` trên bản ghi đó. Ra 17:05 được đánh giá đúng giờ, không về sớm; ra 16:30 là về sớm. Chưa có giờ ra thì trạng thái là đang làm việc.

**Lần tiếp theo:** Nếu cả giờ vào và ra đều tồn tại, hệ thống trả kết quả đã hoàn tất, không tạo lượt thứ ba theo logic hiện tại. Không có trạng thái tăng ca. Ví dụ trên mô tả nghiệp vụ đã có mã xử lý; việc tự động kích hoạt bằng lượt quét thiết bị còn phải tích hợp.

## 7. Ảnh bằng chứng chấm công

`AnhVao`, `AnhRa` lưu ảnh lúc ghi nhận vào/ra, tách với ảnh đăng ký khuôn mặt. Web có ảnh thu nhỏ và xem ảnh khi có dữ liệu. Nếu camera không cung cấp được ảnh, nghiệp vụ hiện vẫn có thể ghi nhận giờ với ảnh để trống.

Trong Web PHP, ảnh quản trị yêu cầu quyền Admin. Ảnh cá nhân chỉ được trả khi bản ghi chấm công thuộc `MaNV` trong Session. Điều này ngăn nhân viên xem ảnh người khác chỉ bằng cách thay mã bản ghi.

## 8. Lịch sử sức khỏe và cảnh báo

Lịch sử sức khỏe lưu mã nhân viên, nhịp tim, SpO2 và thời gian trong `LichSuSucKhoe`. Quản trị viên tra cứu theo nhân viên, từ khóa, khoảng ngày; nhân viên xem lịch sử của mình.

Cảnh báo được lưu trong `CanhBao`, gồm người liên quan, loại, nội dung và thời gian; có thể liên kết trạng thái hoặc thiết bị. `LichSuTrangThai` lưu trạng thái theo nhân viên; `DanhMucBieuHien`, `LoaiCanhBao` cung cấp nhãn và nhóm cảnh báo. Web hỗ trợ tra cứu lịch sử, lọc loại cảnh báo.

Flask đã có API nhận nhịp tim và SpO2 nhưng vẫn ghi vào SQL Server. Chưa có luồng nhận cảm biến tương đương trong PHP để ghi trực tiếp MariaDB. Việc lưu chỉ số cũng chưa tự tạo cảnh báo bất thường sức khỏe theo chuỗi thời gian.

## 9. AI hỗ trợ phát hiện trạng thái

Source Python sử dụng MediaPipe FaceMesh: camera → landmark → tính EAR và góc nghiêng đầu → xác định trạng thái → lưu lịch sử/cảnh báo. EAR dưới 0,25 trong ít nhất 20 frame liên tiếp được gán nhãn hỗ trợ phát hiện buồn ngủ; nhánh góc nghiêng trên 30° hỗ trợ phát hiện gục đầu.

Chỉ khi đã gán nhân viên đang theo dõi, hệ thống mới ghi dữ liệu cho người đó. Trong Flask, check-in gán nhân viên và check-out đúng người xóa gán. Lịch sử trạng thái được giới hạn khoảng 5 giây/lần; cảnh báo cùng loại có thời gian chờ 30 giây, ghi bằng luồng nền.

Phân tích hiện được gọi trong luồng video Flask, chưa phải bộ giám sát độc lập cho toàn bộ nhân viên. Nếu MediaPipe lỗi, cơ chế dự phòng chỉ giữ ứng dụng hoạt động, không thực hiện phát hiện. Các nhãn là dấu hiệu hỗ trợ, không phải chẩn đoán y tế; phần AI trạng thái chưa phải thiết kế cuối cùng.

## 10. Trang của nhân viên và tra cứu

Trang cá nhân PHP cho phép xem hồ sơ, ca hôm nay, giờ vào/ra, trạng thái, ảnh bằng chứng, lịch sử chấm công, lịch sử sức khỏe và cảnh báo. Nhân viên có thể lọc lịch sử chấm công theo khoảng ngày.

Mã nhân viên được lấy từ Session và đưa vào điều kiện truy vấn, không lấy tùy ý từ yêu cầu để xem dữ liệu người khác. Quản trị viên tra cứu chấm công theo nhân viên, từ khóa, một ngày hoặc khoảng ngày; kết quả gồm ca, giờ, trạng thái và ảnh nếu có. Đây là dữ liệu đã lưu, không phải bằng chứng rằng thiết bị đang kết nối.

## 11. Tổng quan dành cho quản trị viên

Web tổng hợp số nhân viên, người đã đăng ký khuôn mặt, có phân ca, đã chấm công, đang làm việc, đi trễ, về sớm và chưa chấm công trong ngày. Có thống kê lượt vào/ra trong bảy ngày và cảnh báo gần đây.

Số chưa chấm công hiện được đếm trên danh sách toàn bộ nhân viên, gồm cả người chưa phân ca, nên không thể hiểu hoàn toàn là số người vắng theo lịch. Chức năng tổng quan phục vụ theo dõi và đối chiếu dữ liệu.

## 12. Thiết bị và mức độ tích hợp

Web hiện đọc và hiển thị `MaTB`, `LoaiTB`, `TrangThai` từ danh mục thiết bị. Chưa có mã chứng minh ESP/camera chấm công thực tế đã truyền hình ảnh và số đo xuyên suốt. Việc kết nối thiết bị sẽ được hoàn thiện ở giai đoạn tích hợp; camera local hiện do Flask quản lý một nguồn dùng chung.

Phần Web/database đã có quản lý hồ sơ, tài khoản, ca, phân ca, nghiệp vụ chấm công, ảnh và tra cứu. Phần AI đã có trích xuất mẫu, kiểm tra tư thế, so khớp và phân tích trạng thái. Tuy nhiên, cần nối nhận diện với chấm công, thống nhất dữ liệu PHP/Python và kiểm thử thiết bị thật. Cầu nối tải mẫu từ PHP còn gọi hàm phản hồi chưa được định nghĩa, nên chưa thể coi việc đồng bộ mẫu sang AI là hoàn chỉnh.

## 13. Luồng hoạt động thực tế của hệ thống

Với nhân viên mới, quản trị viên tạo hồ sơ và tài khoản, thu đủ năm tư thế khuôn mặt rồi phân ca theo ngày. Khi đến làm việc, luồng mục tiêu là quét mặt để xác định danh tính và chuyển sang check-in. Hiện mã nhận diện và mã chấm công đã có riêng; bước chuyển tự động này chưa hoàn thiện, nên chưa thể khẳng định chỉ quét mặt là chấm công được.

Trong thời gian làm việc, dữ liệu sức khỏe và trạng thái được gắn nhân viên để lưu, tra cứu khi nguồn thu và dịch vụ tương ứng hoạt động. Cuối ca, danh tính được cung cấp lần nữa để cập nhật check-out; quản trị viên và nhân viên xem lịch sử theo quyền. Như vậy, phần quản lý và quy tắc nghiệp vụ đã có source, còn chuỗi thiết bị → nhận diện → chấm công → theo dõi cần được tích hợp, kiểm chứng trước khi vận hành thực tế.
