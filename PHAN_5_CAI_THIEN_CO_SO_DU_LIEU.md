# 5 Cải thiện cơ sở dữ liệu và tác động đến hệ thống

**Hồ sơ và tài khoản:** Để thông tin đăng nhập không lẫn với hồ sơ, NhanVien lưu thông tin nhân viên, TaiKhoan lưu tên đăng nhập và mật khẩu, liên kết qua mã nhân viên. Đổi tài khoản không phải sửa hồ sơ; vai trò của nhân viên được dùng để phân quyền. Tên đăng nhập không được trùng, giúp xác định đúng tài khoản khi đăng nhập.

**Mẫu khuôn mặt:** Một ảnh trong hồ sơ không đủ để quản lý nhiều mẫu. FaceEmbedding lưu riêng dữ liệu khuôn mặt và ảnh mẫu, nhiều bản ghi cùng thuộc một nhân viên. Nhờ đó có thể đăng ký nhiều góc, đăng ký lại mà không ảnh hưởng hồ sơ hay lịch sử chấm công. Bộ mới lưu lỗi thì bộ cũ được giữ lại.

**Ca làm việc và phân ca:** Để không phải ghi giờ làm vào từng hồ sơ, CaLamViec giữ danh mục ca, còn PhanCaNhanVien ghi ai làm ca nào vào ngày nào. Một ca dùng được cho nhiều người; đổi ca theo ngày không phải sửa nhân viên. Ràng buộc mã nhân viên và ngày làm việc ngăn phân ca trùng; phân lại sẽ cập nhật ca đã có. Giờ ca là căn cứ đánh giá đi trễ, về sớm.

**Giữ lịch sử ca:** Xóa ca cũ có thể làm mất căn cứ tra cứu. Trường TrangThai cho phép ngừng sử dụng ca rồi kích hoạt lại. Code chặn xóa ca còn phân công hoặc chấm công và chặn đổi giờ ca đã có chấm công, giúp giữ cách đánh giá lịch sử.

**Giờ và ảnh chấm công:** Để giờ vào, giờ ra không thành hai dữ liệu rời, ChamCong lưu cả hai trong cùng bản ghi. AnhVao và AnhRa đi kèm từng thời điểm nếu chụp được ảnh, giúp Admin đối chiếu khi nhân viên thắc mắc. Ảnh này tách khỏi ảnh đăng ký khuôn mặt; lịch sử ngày làm việc dễ tra cứu hơn.

**Lịch sử quét bị từ chối:** Quét không thành công cần có thông tin để kiểm tra. LichSuQuet đã được bổ sung để lưu thời gian, lý do, ảnh, nhân viên nếu xác định được, thiết bị và ca nếu có. Dữ liệu lỗi được lưu riêng, tránh lẫn với chấm công hợp lệ. Phần ghi đã có cơ chế chỉ lưu một lần trong 30 giây khi cùng thiết bị, lý do và nhân viên nếu biết, giảm bản ghi và ảnh dư. Tuy nhiên, luồng quét thực tế chưa gọi phần ghi này tự động; khả năng tra cứu áp dụng khi lịch sử đã được ghi.

**Sức khỏe và cảnh báo:** Để không chỉ giữ một số đo hiện tại, LichSuSucKhoe lưu mã nhân viên, nhịp tim, SpO2 và thời gian thành nhiều bản ghi, thuận tiện xem lại và lọc theo ngày. LoaiCanhBao giữ danh mục loại; CanhBao ghi từng lần phát sinh. Cách tách này giảm lặp tên loại, hỗ trợ lọc và bổ sung loại cảnh báo.

**Liên kết và bỏ dữ liệu dư:** Các bảng dùng mã nhân viên, ca, thiết bị và vai trò để liên kết, hạn chế tham chiếu tới đối tượng không tồn tại và giúp truy ra dữ liệu liên quan. Schema hiện tại đã bỏ bảng ThongSoMoiTruong; code đang dùng không còn truy vấn phần môi trường, giúp giảm dữ liệu và chức năng dư.

Sau các thay đổi, dữ liệu được chia rõ theo nhân viên, tài khoản, khuôn mặt, ca, phân ca, chấm công, lịch sử quét, sức khỏe và cảnh báo. Việc tách dữ liệu giúp giảm trùng lặp, dễ quản lý, mở rộng và tìm lỗi, đồng thời giữ lịch sử và hạn chế ảnh hưởng giữa các chức năng.
