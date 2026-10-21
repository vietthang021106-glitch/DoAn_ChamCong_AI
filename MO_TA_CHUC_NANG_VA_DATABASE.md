# MÔ TẢ CHỨC NĂNG VÀ DATABASE

## 1. Luồng hoạt động tổng thể

Luồng nghiệp vụ gồm: quản trị viên tạo nhân viên và tài khoản → đăng ký khuôn mặt → phân ca theo ngày → ghi nhận vào/ra → lưu dữ liệu sức khỏe, cảnh báo khi phát sinh → quản trị viên hoặc nhân viên xem lại.

Tài liệu mô tả Web PHP và schema MariaDB trong source local. Mã nhân viên `MaNV` liên kết hồ sơ với tài khoản, mẫu khuôn mặt, phân ca và lịch sử. Chức năng quản lý đã có mã xử lý; bước nhận diện tự động chuyển sang chấm công và kết nối thiết bị thực tế chưa hoàn chỉnh.

## 2. Đăng nhập và phân quyền

Người dùng nhập tên đăng nhập, mật khẩu. Hệ thống tìm trong `TaiKhoan`, xác minh mật khẩu, lấy `MaNV` để đọc `NhanVien`, rồi lấy `MaVaiTro` để xác định vai trò trong `VaiTro`. Sai thông tin thì không tạo phiên đăng nhập.

Đăng nhập hợp lệ tạo Session mới, lưu mã tài khoản, mã nhân viên, tên và vai trò; không lưu mật khẩu vào Session. Admin được vào chức năng quản lý; nhân viên vào Trang của tôi. Quyền được kiểm tra phía máy chủ. Đăng xuất hủy Session.

`VaiTro` lưu danh mục vai trò, một vai trò áp dụng cho nhiều nhân viên qua `NhanVien.MaVaiTro`. Tài khoản gắn hồ sơ qua `TaiKhoan.MaNV`. Các biểu mẫu thay đổi dữ liệu PHP còn kiểm tra mã CSRF trước khi xử lý.

## 3. Quản lý nhân viên và tài khoản

Admin thêm họ tên, vai trò, tên đăng nhập và mật khẩu. Hệ thống kiểm tra thông tin, tên đăng nhập trùng và xác nhận mật khẩu. Sau đó tạo `NhanVien`, lấy `MaNV` mới, rồi tạo `TaiKhoan` trỏ đến mã đó. Hai thao tác nằm trong cùng transaction: thành công thì commit; tạo tài khoản lỗi thì rollback, tránh để lại hồ sơ không có tài khoản.

`NhanVien` lưu hồ sơ và vai trò; `TaiKhoan` lưu thông tin đăng nhập; `VaiTro` xác định nhóm quyền. Mật khẩu tạo mới được băm trước khi lưu. Khi sửa, Admin có thể đổi họ tên, vai trò, tên đăng nhập và mật khẩu. Không nhập mật khẩu mới thì giữ mật khẩu cũ; hồ sơ cũ chưa có tài khoản có thể được bổ sung tài khoản.

Danh sách cho tìm theo mã, họ tên hoặc tên đăng nhập, đồng thời hiển thị tình trạng tài khoản và số mẫu khuôn mặt. Trạng thái đã đăng ký được xác định từ việc có bản ghi `FaceEmbedding` của nhân viên đó.

## 4. Đăng ký khuôn mặt

Nhân viên mới chưa có mẫu khuôn mặt. Admin chọn nhân viên và bắt đầu đăng ký; hệ thống kiểm tra hồ sơ tồn tại và dịch vụ xử lý sẵn sàng. Source hiện thu năm mẫu: chính diện, nghiêng trái, nghiêng phải, ngẩng nhẹ và cúi nhẹ.

Mỗi mẫu phải có đúng một khuôn mặt và đúng hướng yêu cầu. Mẫu hợp lệ được gắn với nhân viên trong phiên thu mẫu. **Chỉ khi đủ năm mẫu và hoàn tất lưu**, hệ thống mới ghi cả bộ vào `FaceEmbedding`, không ghi từng mẫu ngay khi chụp.

Mỗi bản ghi có `MaEmbedding`, `MaNV`, `VectorData`, `AnhKhuonMat`, `SoChieu`, `ThoiGianTao`. `VectorData` là dữ liệu đặc trưng dùng nhận diện; `AnhKhuonMat` là ảnh mẫu tương ứng. `SoChieu` hiện là 512. Quan hệ `NhanVien` 1–n `FaceEmbedding` cho phép một người có nhiều mẫu.

Khi đăng ký lại, bộ cũ được giữ trong lúc thu bộ mới. Chỉ sau khi đủ mẫu hợp lệ, thao tác thay thế mới diễn ra trong transaction; lỗi ghi dữ liệu thì rollback. Hủy phiên chưa lưu không làm mất bộ mẫu cũ. Admin cũng có thể xóa toàn bộ đăng ký của nhân viên.

## 5. Quản lý ca làm việc

`CaLamViec` lưu `MaCa`, tên ca, giờ bắt đầu, giờ kết thúc và trạng thái. Admin có thể tạo, sửa, ngừng sử dụng, kích hoạt lại hoặc xóa ca chưa được sử dụng. Giờ kết thúc phải sau giờ bắt đầu; hiện chưa hỗ trợ ca qua đêm.

Ca đã có phân ca hoặc chấm công tham chiếu thì không được xóa. Thay vào đó có thể ngừng sử dụng để giữ lịch sử. Ca ngừng sử dụng không được chọn cho phân ca mới. Nếu ca đã có chấm công, hệ thống chỉ cho đổi tên, khóa thay đổi giờ nhằm tránh làm sai kết quả đi trễ, về sớm của dữ liệu cũ.

## 6. Phân ca nhân viên

Admin chọn nhân viên, ca đang sử dụng và ngày làm việc. Hệ thống lưu `MaNV`, `MaCa`, `NgayLamViec` vào `PhanCaNhanVien`. Mỗi bản ghi trả lời: ai làm ca nào vào ngày nào.

Một nhân viên có nhiều phân ca qua các ngày; một ca được phân cho nhiều nhân viên. Vì vậy, cả `NhanVien` và `CaLamViec` đều có quan hệ 1–n với `PhanCaNhanVien`.

Ràng buộc duy nhất trên `MaNV + NgayLamViec` giới hạn một nhân viên một ca mỗi ngày. Phân lại cùng nhân viên/ngày cập nhật ca trên bản ghi hiện có. Hủy phân ca bị chặn nếu ngày đó đã phát sinh chấm công. Không có phân ca hôm nay thì nghiệp vụ chấm công trả lỗi.

## 7. Chấm công và ảnh bằng chứng

Giả sử NV001 làm ca 08:00–17:00. Khi có danh tính và `MaNV`, hệ thống tìm phân ca trong ngày rồi kiểm tra `ChamCong`. API hiện nhận mã nhân viên từ bên gọi; chưa tự bắt buộc một kết quả nhận diện khuôn mặt trước khi ghi.

**Lần đầu — check-in:** Chưa có chấm công hôm nay thì tạo bản ghi gồm `MaNV`, `MaCa`, `MaTB`, `GioVao`, `AnhVao`; `GioRa`, `AnhRa` để NULL. Giờ vào lấy theo thời gian ghi nhận. Vào 07:55 hoặc đúng 08:00 là đúng giờ; 08:10 là đi trễ. Quy tắc là `GioVao <= GioBatDau` đúng giờ, ngược lại đi trễ; không có khoảng cho phép đi muộn.

**Lần thứ hai — check-out:** Đã có `GioVao`, còn `GioRa = NULL` thì cập nhật chính bản ghi đó, lưu `GioRa`, `AnhRa`. Ra 16:30 là về sớm vì trước 17:00; ra đúng 17:00 hoặc 17:05 được đánh giá đúng giờ theo logic hiện tại. Chưa có giờ ra thì hiển thị đang làm việc.

**Sau khi đủ vào/ra:** Hệ thống trả kết quả đã hoàn tất trong ngày, không tạo lượt mới theo nghiệp vụ hiện có. Không có trạng thái tăng ca. Các trạng thái đúng giờ, đi trễ, về sớm được tính từ giờ chấm công và giờ ca khi đọc dữ liệu.

`ChamCong.MaNV`, `MaCa`, `MaTB` lần lượt liên kết `NhanVien`, `CaLamViec`, `ThietBi`. `AnhVao`, `AnhRa` lưu ảnh bằng chứng tương ứng, tách với ảnh đăng ký khuôn mặt. Không lấy được ảnh thì code vẫn có thể ghi giờ và để ảnh trống.

Web quản trị hỗ trợ xem ảnh thu nhỏ và ảnh chi tiết. Nhân viên chỉ xem ảnh thuộc bản ghi của mình: truy vấn kiểm tra đồng thời `MaCC` và `MaNV` trong Session. Admin có thể tra cứu chấm công theo nhân viên, từ khóa và ngày hoặc khoảng ngày.

## 8. Lịch sử sức khỏe

`LichSuSucKhoe` lưu `MaNV`, `NhipTim`, `SpO2`, `ThoiGian`, mỗi bản ghi có mã riêng. Một nhân viên có nhiều bản ghi theo thời gian, liên kết bằng `MaNV`. Admin lọc theo nhân viên, từ khóa, khoảng ngày; nhân viên xem lịch sử của chính mình.

Web PHP hiện đọc lịch sử trong MariaDB. API nhận chỉ số ở Flask cũ vẫn ghi SQL Server, nên chưa thể coi số đo nhận từ nguồn đó tự xuất hiện trên Web PHP. Phần tiếp nhận, ghi dữ liệu thiết bị vào cùng nguồn còn cần tích hợp; thao tác xem lịch sử không tự tạo số đo mới.

## 9. Cảnh báo và lịch sử trạng thái

`DanhMucBieuHien` chứa danh mục biểu hiện; `LichSuTrangThai` ghi nhân viên, biểu hiện và thời gian. `LoaiCanhBao` chứa danh mục loại; `CanhBao` lưu cảnh báo thực tế gồm người liên quan, loại, nội dung, thời gian và liên kết tùy chọn đến trạng thái, thiết bị.

Phần ghi cảnh báo trạng thái trong source Python cũ tạo lịch sử trạng thái, lấy `MaTT`, rồi tạo cảnh báo gắn `MaNV`, `MaLoaiCB`, `MaTT` và có thể `MaTB`. Web PHP đọc các bản ghi MariaDB, nối danh mục để hiển thị trong Sức khỏe & Cảnh báo. Admin lọc theo nhân viên, ngày, loại; nhân viên chỉ xem cảnh báo của mình.

Không phải mọi số đo sức khỏe đều tự tạo cảnh báo. Luồng ghi tự động từ dịch vụ cũ sang database của Web PHP chưa được thống nhất.

## 10. Thông tin thiết bị

`ThietBi` lưu `MaTB`, `LoaiTB`, `TrangThai`. Web hiện hiển thị danh sách cho Admin, chưa có đầy đủ thao tác thêm, sửa, xóa thiết bị qua chức năng này. `ChamCong.MaTB` tham chiếu thiết bị được ghi cho lượt chấm công; `CanhBao.MaTB` có thể liên kết thiết bị liên quan. Danh mục không tự chứng minh thiết bị đang truyền dữ liệu; kết nối ESP/camera thực tế chưa hoàn thiện.

## 11. Trang của tôi

Nhân viên đăng nhập rồi mở Trang của tôi. Hệ thống lấy `MaNV` từ Session, không lấy mã nhân viên tùy ý từ URL. Từ đó đọc hồ sơ `NhanVien`, tìm phân ca trong `PhanCaNhanVien`, nối `CaLamViec`, lấy giờ vào/ra và ảnh từ `ChamCong`.

Trang này còn đọc `LichSuSucKhoe`, `CanhBao` theo cùng mã nhân viên, cho xem lịch sử chấm công theo khoảng ngày. Mỗi truy vấn cá nhân giới hạn đúng chủ sở hữu; yêu cầu xem ảnh cũng kiểm tra lại quyền. Admin được chuyển về Dashboard khi mở trang này.

## 12. Dashboard

Dashboard tổng hợp tổng nhân viên, số người có mẫu khuôn mặt, có phân ca hôm nay, đã chấm công, đang làm việc, đi trễ, về sớm và chưa chấm công. Ngoài ra có hoạt động vào/ra bảy ngày, cảnh báo gần đây.

Dữ liệu lấy từ `NhanVien`, `FaceEmbedding`, `PhanCaNhanVien`, `CaLamViec`, `ChamCong`, `CanhBao` và danh mục liên quan. Dashboard không tạo dữ liệu mới. Số chưa chấm công hiện đếm trên toàn bộ nhân viên, kể cả người chưa được phân ca, nên không tương đương hoàn toàn số vắng theo lịch.

## 13. Cơ sở dữ liệu và mối quan hệ giữa các bảng

Schema MariaDB hiện định nghĩa 13 bảng phục vụ các chức năng trên:

| Bảng | Chức năng |
|------|-----------|
| VaiTro | Danh mục vai trò, quyền truy cập |
| NhanVien | Hồ sơ nhân viên và vai trò |
| TaiKhoan | Tên đăng nhập, mật khẩu của nhân viên |
| FaceEmbedding | Nhiều mẫu đặc trưng và ảnh khuôn mặt |
| CaLamViec | Danh mục ca, giờ và trạng thái sử dụng |
| PhanCaNhanVien | Nhân viên làm ca nào, ngày nào |
| ChamCong | Giờ vào/ra, ca, thiết bị và ảnh bằng chứng |
| ThietBi | Mã, loại và trạng thái thiết bị |
| LichSuSucKhoe | Lịch sử nhịp tim, SpO2 theo nhân viên |
| LoaiCanhBao | Danh mục loại cảnh báo |
| CanhBao | Cảnh báo thực tế phát sinh |
| LichSuTrangThai | Trạng thái nhân viên theo thời gian |
| DanhMucBieuHien | Danh mục biểu hiện được ghi nhận |

## 14. Mối quan hệ bảng

`NhanVien.MaVaiTro → VaiTro.MaVaiTro` tạo quan hệ nhiều nhân viên cùng một vai trò. `TaiKhoan.MaNV → NhanVien.MaNV` gắn tài khoản với hồ sơ. Luồng Web thường quản lý một tài khoản cho mỗi người, nhưng schema không đặt UNIQUE trên `TaiKhoan.MaNV`, nên chưa ràng buộc quan hệ 1–1 ở database.

`FaceEmbedding`, `LichSuSucKhoe`, `LichSuTrangThai` cùng tham chiếu `NhanVien` qua `MaNV`, mỗi người có nhiều mẫu hoặc bản ghi lịch sử. `PhanCaNhanVien` tham chiếu nhân viên bằng `MaNV`, tham chiếu ca bằng `MaCa`; `ChamCong` cũng tham chiếu nhân viên, ca và thêm thiết bị qua `MaTB`.

`LichSuTrangThai.MaBieuHien → DanhMucBieuHien.MaBieuHien`. Còn `CanhBao` liên kết `NhanVien` qua `MaNV`, `LoaiCanhBao` qua `MaLoaiCB`, `LichSuTrangThai` qua `MaTT`, `ThietBi` qua `MaTB`. `MaTT`, `MaTB` có thể để trống. Nhờ vậy, cảnh báo vẫn có thể lưu khi không gắn một lịch sử trạng thái hoặc thiết bị cụ thể.

## 15. Luồng dữ liệu thực tế

Ví dụ Nguyễn Văn A có mã hiển thị NV001, tương ứng `MaNV = 1`:

1. Admin thêm A và chọn vai trò nhân viên. Hệ thống tạo `NhanVien`, lấy mã mới.
2. Tài khoản được tạo trong cùng transaction, `TaiKhoan.MaNV` trỏ đến A. Lỗi tạo tài khoản thì hủy cả hai thao tác.
3. Admin thu năm tư thế khuôn mặt. Đủ mẫu hợp lệ mới lưu năm bản ghi `FaceEmbedding` cùng `MaNV` của A.
4. Admin phân ca 08:00–17:00 cho ngày làm việc. `PhanCaNhanVien` lưu mã A, mã ca và ngày; thông tin giờ nằm ở `CaLamViec`.
5. Khi yêu cầu chấm công cung cấp mã A, hệ thống tìm phân ca hôm nay. Chưa có lượt vào thì tạo `ChamCong`, lưu `GioVao`, `AnhVao` nếu có, cùng mã ca và thiết bị.
6. Yêu cầu tiếp theo cập nhật cùng bản ghi bằng `GioRa`, `AnhRa`. Đủ vào/ra thì lần gọi tiếp trả đã hoàn tất.
7. Khi có nguồn ghi dữ liệu sức khỏe, mỗi lần ghi tạo một `LichSuSucKhoe` theo mã A. Nếu có cảnh báo trạng thái, phần ghi tạo `LichSuTrangThai` rồi `CanhBao` liên quan; các nguồn này cần dùng đúng database mà Web đọc.
8. Admin mở Dashboard hoặc tra cứu để tổng hợp dữ liệu. A đăng nhập, hệ thống lấy mã trong Session để đọc đúng hồ sơ, ca, chấm công, sức khỏe và cảnh báo của A.
